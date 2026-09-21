#!/usr/bin/env python3
"""Backend server that serves frontend and proxies requests to LangGraph API.

No external dependencies required - uses only Python standard library.
"""

from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.request
import urllib.error
import json
import os

LANGGRAPH_API = "http://localhost:8123"

class ProxyHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/'):
            self.proxy_request()
        else:
            # Serve static files
            self.serve_static_file()

    def do_POST(self):
        if self.path.startswith('/api/'):
            self.proxy_request()
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def serve_static_file(self):
        """Serve static files from current directory."""
        # Map / to /index.html
        path = self.path
        if path == '/':
            path = '/index.html'

        # Remove query string
        path = path.split('?')[0]

        # Security: prevent directory traversal
        if '..' in path:
            self.send_error(403, "Forbidden")
            return

        # Get file path
        file_path = '.' + path

        # Check if file exists
        if not os.path.isfile(file_path):
            self.send_error(404, "File not found")
            return

        # Determine content type
        content_types = {
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
        }
        ext = os.path.splitext(file_path)[1].lower()
        content_type = content_types.get(ext, 'application/octet-stream')

        try:
            # Read and serve file
            with open(file_path, 'rb') as f:
                content = f.read()

            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', len(content))
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(content)

        except Exception as e:
            self.send_error(500, f"Error reading file: {str(e)}")

    def proxy_request(self):
        """Proxy requests to LangGraph API."""
        # Remove /api prefix and forward to LangGraph
        api_path = self.path[4:]  # Remove '/api'
        url = f"{LANGGRAPH_API}{api_path}"

        try:
            # Read request body if POST
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length) if content_length > 0 else None

            # Create request
            req = urllib.request.Request(
                url,
                data=body,
                method=self.command,
                headers={'Content-Type': 'application/json'} if body else {}
            )

            # Make request to LangGraph API
            with urllib.request.urlopen(req, timeout=300) as response:
                # Send response
                self.send_response(response.status)

                # Copy headers
                for key, value in response.headers.items():
                    if key.lower() not in ['content-encoding', 'transfer-encoding']:
                        self.send_header(key, value)

                # Add CORS headers
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                # Stream response body
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, f"LangGraph API Error: {e.reason}")
        except urllib.error.URLError as e:
            self.send_error(502, f"Cannot connect to LangGraph API at {LANGGRAPH_API}: {e.reason}")
        except Exception as e:
            self.send_error(500, f"Proxy error: {str(e)}")


    def log_message(self, format, *args):
        """Custom logging."""
        if self.path.startswith('/api/'):
            print(f"[PROXY] {format % args}")
        else:
            print(f"[STATIC] {format % args}")

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    port = 8080
    server = HTTPServer(('localhost', port), ProxyHandler)

    print("=" * 60)
    print("LangGraph Frontend Server")
    print("=" * 60)
    print(f"Frontend:      http://localhost:{port}")
    print(f"LangGraph API: {LANGGRAPH_API}")
    print("=" * 60)
    print("\nMake sure LangGraph server is running:")
    print("  langgraph up")
    print("\nThen open: http://localhost:{port}")
    print("=" * 60)
    print(f"\nServing files from: {os.getcwd()}")
    print("Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nShutting down server...")
        server.shutdown()
