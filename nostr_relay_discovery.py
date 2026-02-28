#!/usr/bin/env python3
"""
Nostr Relay Discovery Tool

This tool discovers Nostr relays by performing breadth-first search through
follow lists (kind 3 events) and analyzing relay tags to build a network map.
"""

import asyncio
import json
import logging
import re
import time
import argparse
import secrets
import base64
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Set, List, Dict, Optional, Tuple
from urllib.parse import urlparse
import websockets
import websockets.exceptions


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Save progress every N relays processed
SAVE_POINT = 10


@dataclass
class RelayDiscoveryStats:
    """Statistics for the relay discovery process"""
    total_relays_found: int = 0
    functioning_relays: int = 0
    events_processed: int = 0
    existing_relays_verified: int = 0
    existing_relays_failed: int = 0
    start_time: float = field(default_factory=time.time)
    
    def print_stats(self):
        """Print current statistics"""
        elapsed = time.time() - self.start_time
        print(f"\n=== Discovery Statistics ===")
        print(f"Elapsed time: {elapsed:.2f} seconds")
        print(f"Total relays found: {self.total_relays_found}")
        print(f"Functioning relays: {self.functioning_relays}")
        print(f"Events processed: {self.events_processed}")
        if self.existing_relays_verified > 0 or self.existing_relays_failed > 0:
            print(f"Existing relays verified: {self.existing_relays_verified}")
            print(f"Existing relays failed verification: {self.existing_relays_failed}")
        print(f"Success rate: {(self.functioning_relays/max(1, self.total_relays_found)*100):.1f}%")


class NostrRelayDiscovery:
    """Nostr relay discovery tool using breadth-first search through follow lists"""
    
    def __init__(self, initial_relay: str, max_depth: int = 3, connection_timeout: int = 5, output_file: str = "relay_discovery_results.json", save_point: int = SAVE_POINT, batch_size: int = 10):
        self.initial_relay = initial_relay
        self.max_depth = max_depth
        self.connection_timeout = connection_timeout
        self.output_file = output_file
        self.save_point = save_point
        self.batch_size = batch_size
        
        # Discovery state
        self.to_visit: deque = deque()  # (relay_url, depth) - will be populated by load_existing_results
        self.to_visit_set: Set[str] = set()
        self.visited_relays: Set[str] = set()
        self.functioning_relays: Set[str] = set()
        
        # Statistics
        self.stats = RelayDiscoveryStats()
        
        # Regex for validating relay URLs
        self.relay_url_pattern = re.compile(
            r'^wss?://[a-zA-Z0-9.-]+(?:\:[0-9]+)?(?:/[a-zA-Z0-9._~:/?#[\]@!$&\'()*+,;=-]*)?$'
        )
    
    def is_valid_relay_url(self, url: str) -> bool:
        """Validate if a URL looks like a valid relay URL"""
        if not url or not isinstance(url, str):
            return False
        
        # Clean up the URL
        url = url.strip()
        
        # Check basic format
        if not self.relay_url_pattern.match(url):
            return False
        
        # Parse and validate
        try:
            parsed = urlparse(url)
            return (
                parsed.scheme in ['ws', 'wss'] and
                parsed.netloc and
                len(parsed.netloc) > 0
            )
        except Exception:
            return False
    
    def normalize_relay_url(self, url: str) -> str:
        """Normalize relay URL (remove trailing slashes, etc.)"""
        url = url.strip().lower()
        match = re.match(r'^(wss://[^/]+)/?$', url)

        if match:
            matched_url = match.group(1)
            logger.debug(f"matched url: {matched_url}")
            return matched_url
        else:
            return ''
    
    def generate_subscription_id(self) -> str:
        """Generate a random subscription ID using 16 random bytes encoded as base64"""
        random_bytes = secrets.token_bytes(16)
        return base64.b64encode(random_bytes).decode()
    
    async def test_relay_connection(self, relay_url: str) -> bool:
        """Test if a relay is functioning by attempting to connect and validate Nostr protocol responses"""
        try:
            logger.debug(f"Testing connection to {relay_url}")
            
            async with websockets.connect(
                relay_url,
                open_timeout=self.connection_timeout,
                close_timeout=5,
                max_size=2**20,  # 1MB max message size
                ping_interval=None  # Disable ping
            ) as websocket:
                # Send a simple REQ to test functionality
                subscription_id = self.generate_subscription_id()
                test_filter = {
                    "kinds": [1],
                    "limit": 1
                }
                req_msg = ["REQ", subscription_id, test_filter]
                await websocket.send(json.dumps(req_msg))
                logger.debug(f"Sent REQ with subscription ID: {subscription_id}")
                
                # Wait for a response and validate it's a proper Nostr protocol message
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    logger.debug(f"Received response: {response[:200]}...")  # Log first 200 chars
                    
                    try:
                        data = json.loads(response)
                        
                        # Check if it's a valid Nostr protocol message
                        if not isinstance(data, list) or len(data) < 2:
                            logger.debug(f"Invalid Nostr message format from {relay_url}: not a list or too short")
                            return False
                        
                        message_type = data[0]
                        message_subscription_id = data[1]
                        
                        # Validate subscription ID matches
                        if message_subscription_id != subscription_id:
                            logger.debug(f"Subscription ID mismatch from {relay_url}: expected {subscription_id}, got {message_subscription_id}")
                            return False
                        
                        # Check for valid Nostr protocol message types
                        if message_type == "EVENT":
                            logger.debug(f"✓ Received EVENT from {relay_url}")
                            # Send CLOSE to clean up
                            close_msg = ["CLOSE", subscription_id]
                            await websocket.send(json.dumps(close_msg))
                            return True
                        elif message_type == "EOSE":
                            logger.warning(f"Received EOSE immediately from {relay_url} - relay has no events (unusual)")
                            # Send CLOSE to clean up
                            close_msg = ["CLOSE", subscription_id]
                            await websocket.send(json.dumps(close_msg))
                            return True
                        elif message_type == "NOTICE":
                            notice_message = data[2] if len(data) > 2 else "unknown"
                            logger.debug(f"Received NOTICE from {relay_url}: {notice_message}")
                            return False
                        else:
                            logger.debug(f"Unexpected message type from {relay_url}: {message_type}")
                            return False
                            
                    except json.JSONDecodeError as e:
                        logger.debug(f"Invalid JSON response from {relay_url}: {e}")
                        return False
                        
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout waiting for response from {relay_url}")
                    return False
                    
        except Exception as e:
            logger.debug(f"Failed to connect to {relay_url}: {e}")
            return False
    
    async def test_relays_connections(self, relay_urls: List[str]) -> Dict[str, bool]:
        """Test multiple relays concurrently and return a dict of relay_url -> functioning status"""
        if not relay_urls:
            return {}
        
        # Filter out blocked relays
        blocked_relays_env = os.getenv('BLOCKED_RELAYS', '')
        blocked_relays = set()
        if blocked_relays_env:
            raw_relays = [relay.strip() for relay in blocked_relays_env.split(',')]
            for relay in raw_relays:
                if relay and self.is_valid_relay_url(relay):
                    normalized_relay = self.normalize_relay_url(relay)
                    if normalized_relay:
                        blocked_relays.add(normalized_relay)
        
        filtered_relays = []
        blocked_count = 0
        for relay_url in relay_urls:
            normalized_url = self.normalize_relay_url(relay_url)
            if normalized_url in blocked_relays:
                logger.info(f"Skipping blocked relay: {relay_url}")
                blocked_count += 1
            else:
                filtered_relays.append(relay_url)
        
        if blocked_count > 0:
            logger.info(f"Filtered out {blocked_count} blocked relays")
        
        if not filtered_relays:
            # Return blocked relays as non-functioning
            return {relay_url: False for relay_url in relay_urls}
        
        logger.info(f"Testing {len(filtered_relays)} relays concurrently")
        
        # Create tasks for concurrent testing
        tasks = []
        for relay_url in filtered_relays:
            task = asyncio.create_task(self.test_relay_connection(relay_url))
            tasks.append((relay_url, task))
        
        # Wait for all tasks to complete
        results = {}
        for relay_url, task in tasks:
            try:
                is_functioning = await task
                results[relay_url] = is_functioning
                if is_functioning:
                    logger.info(f"✓ Relay {relay_url} is functioning")
                else:
                    logger.warning(f"✗ Relay {relay_url} is not functioning")
            except Exception as e:
                logger.error(f"Error testing relay {relay_url}: {e}")
                results[relay_url] = False
        
        # Add blocked relays as non-functioning to the results
        for relay_url in relay_urls:
            normalized_url = self.normalize_relay_url(relay_url)
            if normalized_url in blocked_relays:
                results[relay_url] = False
        
        functioning_count = sum(1 for status in results.values() if status)
        logger.info(f"Batch test completed: {functioning_count}/{len(relay_urls)} relays functioning")
        
        return results
    
    async def fetch_events(self, relay_url: str) -> List[Dict]:
        """Fetch kind 3 events (follow lists) or kind 10002 (NIP-66) from a relay"""
        follow_events = []
        
        try:
            logger.info(f"Fetching follow lists from {relay_url}")
            
            async with websockets.connect(
                relay_url,
                open_timeout=self.connection_timeout,
                close_timeout=5,
                max_size=2**20
            ) as websocket:
                
                filter_req = {
                    "kinds": [3, 10002],
                    "limit": 300,
                }
                
                subscription_id = self.generate_subscription_id()
                req_msg = ["REQ", subscription_id, filter_req]
                
                await websocket.send(json.dumps(req_msg))
                logger.debug(f"Sent request: {req_msg}")
                
                # Collect events until EOSE
                start_time = time.time()
                timeout_duration = 30.0
                
                while time.time() - start_time < timeout_duration:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        data = json.loads(message)
                        
                        if data[0] == "EVENT" and data[1] == subscription_id:
                            event = data[2]
                            if event.get("kind") == 3 or event.get("kind") == 10002:
                                follow_events.append(event)
                                logger.debug(f"Collected follow event from {event.get('pubkey', 'unknown')[:8]}...")
                        
                        elif data[0] == "EOSE" and data[1] == subscription_id:
                            logger.debug(f"Received EOSE for {subscription_id}")
                            break
                            
                    except asyncio.TimeoutError:
                        continue
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse message from {relay_url}: {e}")
                        continue
                
                # Send CLOSE message
                close_msg = ["CLOSE", subscription_id]
                await websocket.send(json.dumps(close_msg))
                
        except Exception as e:
            logger.error(f"Error fetching follow lists from {relay_url}: {e}")
        
        logger.info(f"Collected {len(follow_events)} follow events from {relay_url}")
        return follow_events

    async def fetch_events_from_relays(self, relay_urls: List[str]) -> Dict[str, List[Dict]]:
        """Fetch events from multiple relays concurrently and return a dict of relay_url -> events"""
        if not relay_urls:
            return {}
        
        logger.info(f"Fetching events from {len(relay_urls)} relays concurrently")
        
        # Create tasks for concurrent event fetching
        tasks = []
        for relay_url in relay_urls:
            task = asyncio.create_task(self.fetch_events(relay_url))
            tasks.append((relay_url, task))
        
        # Wait for all tasks to complete
        results = {}
        for relay_url, task in tasks:
            try:
                events = await task
                results[relay_url] = events
                logger.info(f"✓ Fetched {len(events)} events from {relay_url}")
            except Exception as e:
                logger.error(f"Error fetching events from relay {relay_url}: {e}")
                results[relay_url] = []
        
        total_events = sum(len(events) for events in results.values())
        logger.info(f"Batch fetch completed: {total_events} total events from {len(relay_urls)} relays")
        
        return results

    
    def extract_relays_from_events(self, events: List[Dict]) -> Set[str]:
        """Extract relay URLs from follow list events"""
        relay_urls = set()
        
        # Get blocked relays
        blocked_relays_env = os.getenv('BLOCKED_RELAYS', '')
        blocked_relays = set()
        if blocked_relays_env:
            raw_relays = [relay.strip() for relay in blocked_relays_env.split(',')]
            for relay in raw_relays:
                if relay and self.is_valid_relay_url(relay):
                    normalized_relay = self.normalize_relay_url(relay)
                    if normalized_relay:
                        blocked_relays.add(normalized_relay)
        
        for event in events:
            self.stats.events_processed += 1
            
            # Process tags to find relay information
            tags = event.get('tags', [])
            
            for tag in tags:
                if not isinstance(tag, list) or len(tag) < 2:
                    continue
                
                # Look for 'r' tags (relay tags)
                if tag[0] == 'r' and len(tag) >= 2:
                    potential_relay = tag[1]
                    if self.is_valid_relay_url(potential_relay):
                        normalized_url = self.normalize_relay_url(potential_relay)
                        if normalized_url not in blocked_relays:
                            relay_urls.add(normalized_url)
                        else:
                            logger.debug(f"Skipping blocked relay from events: {normalized_url}")
                
                # Also check 'p' tags for potential relay info in some implementations
                elif tag[0] == 'p' and len(tag) >= 3:
                    # Some implementations put relay info in the 3rd element of p tags
                    if len(tag) > 2 and self.is_valid_relay_url(tag[2]):
                        normalized_url = self.normalize_relay_url(tag[2])
                        if normalized_url not in blocked_relays:
                            relay_urls.add(normalized_url)
                        else:
                            logger.debug(f"Skipping blocked relay from events: {normalized_url}")
        
        return relay_urls
    
    async def load_existing_results(self) -> bool:
        """Load existing results and verify that functioning relays still work"""
        import os
        
        if not os.path.exists(self.output_file):
            logger.info(f"No existing results file found at {self.output_file}, starting fresh")
            # Initialize with just the initial relay
            self.to_visit.append((self.initial_relay, 0))
            self.to_visit_set.add(self.initial_relay)
            return False
        
        try:
            logger.info(f"Loading existing results from {self.output_file}")
            with open(self.output_file, 'r') as f:
                data = json.load(f)
            
            existing_relays = data.get('functioning_relays', [])
            logger.info(f"Found {len(existing_relays)} existing functioning relays to verify")
            
            if not existing_relays:
                logger.info("No existing relays found, starting fresh")
                self.to_visit.append((self.initial_relay, 0))
                self.to_visit_set.add(self.initial_relay)
                return False
            else:
                logger.info("Existing relays found, building on the previous results")
                self.to_visit.extend([(existing_relay, 0) for existing_relay in existing_relays])
                self.to_visit_set.update(existing_relays)
                
        except Exception as e:
            logger.error(f"Error loading existing results: {e}")
            logger.info("Starting fresh due to error")
            self.to_visit.append((self.initial_relay, 0))
            self.to_visit_set.add(self.initial_relay)
            return False
    
    async def discover_relays(self) -> Set[str]:
        """Main discovery method using breadth-first search with concurrent processing"""
        # First, try to load existing results and verify them
        logger.info("Checking for existing results to build upon...")
        await self.load_existing_results()
        
        logger.info(f"Starting relay discovery with batch size {self.batch_size}")
        logger.info(f"Maximum depth: {self.max_depth}")
        
        while self.to_visit:
            # Collect a batch of relays to process
            current_batch = []
            batch_depth_map = {}
            
            # Get up to batch_size relays from the queue
            for _ in range(min(self.batch_size, len(self.to_visit))):
                if not self.to_visit:
                    break
                    
                current_relay, depth = self.to_visit.popleft()
                self.to_visit_set.remove(current_relay)
                
                # Skip if already visited
                if current_relay in self.visited_relays:
                    continue
                    
                # Skip if depth exceeds maximum
                if depth > self.max_depth:
                    logger.info(f"Reached maximum depth {self.max_depth}, stopping exploration")
                    continue
                
                current_batch.append(current_relay)
                batch_depth_map[current_relay] = depth
                self.visited_relays.add(current_relay)
            
            if not current_batch:
                break
            
            logger.info(f"Processing batch of {len(current_batch)} relays")
            
            # Test all relays in the batch concurrently
            test_results = await self.test_relays_connections(current_batch)
            
            # Collect functioning relays for event fetching
            functioning_relays_batch = []
            for relay_url, is_functioning in test_results.items():
                if is_functioning:
                    self.functioning_relays.add(relay_url)
                    self.stats.functioning_relays += 1
                    
                    # Only add to event fetching if we haven't reached max depth
                    depth = batch_depth_map[relay_url]
                    if depth < self.max_depth:
                        functioning_relays_batch.append(relay_url)
            
            # Fetch events from all functioning relays concurrently
            if functioning_relays_batch:
                events_results = await self.fetch_events_from_relays(functioning_relays_batch)
                
                # Process events and extract new relays
                for relay_url, events in events_results.items():
                    if events:
                        depth = batch_depth_map[relay_url]
                        new_relays = self.extract_relays_from_events(events)
                        
                        # Add new relays to visit queue for next depth level
                        for new_relay_url in new_relays:
                            if new_relay_url not in self.visited_relays and new_relay_url not in self.to_visit_set:
                                self.to_visit.append((new_relay_url, depth + 1))
                                self.to_visit_set.add(new_relay_url)
                                self.stats.total_relays_found += 1
                                logger.debug(f"Added {new_relay_url} to visit queue at depth {depth + 1}")
            
            # Save progress periodically
            if len(self.visited_relays) % self.save_point == 0:
                logger.info(f"Progress checkpoint: Saving results after processing {len(self.visited_relays)} relays")
                self.save_results()
            
            # Print periodic statistics
            if len(self.visited_relays) % 10 == 0:
                self.stats.print_stats()
        
        logger.info("Discovery completed!")
        return self.functioning_relays
    
    def save_results(self, output_file: str = None):
        """Save discovery results to a JSON file"""
        if output_file is None:
            output_file = self.output_file
            
        results = {
            "discovery_settings": {
                "initial_relay": self.initial_relay,
                "max_depth": self.max_depth,
                "connection_timeout": self.connection_timeout,
                "save_point": self.save_point,
                "batch_size": self.batch_size,
                "blocked_relays_env": os.getenv('BLOCKED_RELAYS', '')
            },
            "progress_info": {
                "relays_processed": len(self.visited_relays),
                "relays_remaining": len(self.to_visit),
                "discovery_complete": len(self.to_visit) == 0,
                "last_saved": time.time()
            },
            "statistics": {
                "total_relays_found": self.stats.total_relays_found,
                "functioning_relays_count": len(self.functioning_relays),
                "events_processed": self.stats.events_processed,
                "existing_relays_verified": self.stats.existing_relays_verified,
                "existing_relays_failed": self.stats.existing_relays_failed,
                "discovery_duration": time.time() - self.stats.start_time
            },
            "functioning_relays": list(self.functioning_relays)
        }
        
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        logger.info(f"Results saved to {output_file}")


async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description="Discover Nostr relays using breadth-first search")
    parser.add_argument(
        "initial_relay",
        help="Initial relay URL to start discovery from (e.g., wss://relay.damus.io)"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum depth for breadth-first search (default: 3)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="Connection timeout in seconds (default: 5)"
    )
    parser.add_argument(
        "--output",
        default="relay_discovery_results.json",
        help="Output file for results (default: relay_discovery_results.json)"
    )
    parser.add_argument(
        "--save-point",
        type=int,
        default=SAVE_POINT,
        help=f"Save progress every N relays processed (default: {SAVE_POINT})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of relays to process concurrently (default: 10)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Validate initial relay URL
    discovery = NostrRelayDiscovery(
        args.initial_relay, 
        args.max_depth, 
        args.timeout, 
        args.output, 
        args.save_point,
        args.batch_size
    )
    if not discovery.is_valid_relay_url(args.initial_relay):
        print(f"Error: Invalid relay URL: {args.initial_relay}")
        print("Relay URL should start with ws:// or wss://")
        return 1
    
    try:
        # Run discovery
        functioning_relays = await discovery.discover_relays()
        
        # Print final results
        print("\n=== DISCOVERY COMPLETED ===")
        discovery.stats.print_stats()
        
        print(f"\n=== FUNCTIONING RELAYS ({len(functioning_relays)}) ===")
        for relay in sorted(functioning_relays):
            print(f"  {relay}")
        
        # Save results
        discovery.save_results()
        
        return 0
        
    except KeyboardInterrupt:
        print("\nDiscovery interrupted by user")
        discovery.save_results()
        return 1
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
