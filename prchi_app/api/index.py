import sys
import os
from http.server import BaseHTTPRequestHandler

# Add parent directory to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            template_path = os.path.join(root_dir, 'templates', 'index.html')
            with open(template_path, 'r', encoding='utf-8') as f:
                content = f.read()

            body = content.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err = f"Error rendering index: {str(e)}".encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(err)))
            self.end_headers()
            self.wfile.write(err)
