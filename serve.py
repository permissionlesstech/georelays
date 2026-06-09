#!/usr/bin/env python3
"""
BitChat Terminal Local Dev Server

A lightweight development helper to run the GeoRelays terminal locally.
This server automatically filters out 404 background noise from browser extensions,
ad-blockers, or cryptocurrency wallets probing '/api/v1/check' and '/favicon.ico',
keeping your console logs completely clean and uncluttered.
"""

import http.server
import socketserver
import sys

PORT = 8000

class SilentHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        # Extract the raw request line (usually the first argument)
        request_line = args[0] if args else ""
        
        # Suppress noise from automatic probes/extensions
        if "/api/v1/check" in request_line or "favicon.ico" in request_line:
            return
            
        # Log all standard requests cleanly
        super().log_message(format, *args)

def main():
    # Use our custom noise-filtering handler
    Handler = SilentHTTPRequestHandler
    
    # Allow quick port reuse to avoid 'Address already in use' errors on restarts
    socketserver.TCPServer.allow_reuse_address = True
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print("==================================================================")
            print("         B I T C H A T   T E R M I N A L   S E R V E R            ")
            print("==================================================================")
            print(f" [*] Connection Channel established locally.")
            print(f" [*] Mainframe URL : http://localhost:{PORT}")
            print(f" [*] Status        : Suppression active for background / extension noise.")
            print(f" [*] Command       : Press Ctrl+C to terminate server safely.")
            print("==================================================================")
            httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n [!] Connection terminated cleanly. Securing ports.")
        sys.exit(0)

if __name__ == "__main__":
    main()
