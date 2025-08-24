#!/bin/bash

# How many relays to query in parallel
CONCURRENCY=${CONCURRENCY:-10}

# Read relays from stdin or file into array
mapfile -t relays

# Function to test a single relay for kind 20000 support (both read and write)
test_relay() {
    local relay="$1"
    local count
    local post_result
    
    # Test 1: Try to request kind 20000 events and count them
    # Use timeout to avoid hanging on unresponsive relays
    count=$(timeout 10s nak req -k 20000 "$relay" 2>/dev/null | jq -s 'length' 2>/dev/null)
    
    # Check if we got a valid response (number >= 0) for reading
    if [[ ! "$count" =~ ^[0-9]+$ ]]; then
        return 1  # Failed to read kind 20000 events
    fi
    
    # Test 2: Try to post a kind 20000 event
    # Generate a unique test content to avoid duplicate events
    local test_content="test_$(date +%s)_$$"
    
    # Try to post a test kind 20000 event
    post_result=$(timeout 10s nak event -k 20000 --tag n=test --tag g=test --content "$test_content" "$relay" 2>&1)
    
    # Check if the post was successful
    if echo "$post_result" | grep -q "success"; then
        echo "$relay"
    else
        return 1
    fi
}

export -f test_relay

total_relays=${#relays[@]}
batch_size=$((total_relays / CONCURRENCY))
if [ $batch_size -eq 0 ]; then
    batch_size=1
fi

# Process relays in parallel batches
printf '%s\n' "${relays[@]}" | xargs -P "$CONCURRENCY" -I {} bash -c 'test_relay "$@"' _ {}