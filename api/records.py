import sys
import os
import json
from http.server import BaseHTTPRequestHandler

# Add root folder to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import notion_service

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            records = notion_service.query_database_records()
            data = {
                "success": True,
                "count": len(records),
                "reconciled_count": sum(1 for r in records if r.get("rcg")),
                "pending_count": sum(1 for r in records if not r.get("rcg")),
                "records": records,
                "database_id": notion_service.DATABASE_ID
            }
            body = json.dumps(data).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            err_data = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(err_data)))
            self.end_headers()
            self.wfile.write(err_data)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
