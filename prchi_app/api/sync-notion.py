import sys
import os
import json
import base64
from http.server import BaseHTTPRequestHandler

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import notion_service

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if post_data else {}

            page_id = data.get('page_id')
            filename = data.get('filename')
            image_base64 = data.get('image_base64')
            metadata = data.get('metadata', {})
            mark_prchi = data.get('mark_prchi', True)

            if not page_id:
                err_data = json.dumps({"success": False, "error": "Missing page_id"}).encode('utf-8')
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(err_data)
                return

            image_bytes = None
            if image_base64:
                if ',' in image_base64:
                    image_base64 = image_base64.split(',', 1)[1]
                image_bytes = base64.b64decode(image_base64)

            cloud_url = None
            if image_bytes:
                cloud_url = notion_service.upload_image_to_cloud(image_bytes, filename or "prchi_voucher.jpg")

            # Updates Notion row:
            # 1. Sets PRCHI checkbox: True (if mark_prchi). Touches NO remarks or other columns.
            # 2. Appends image block to side peek (preserving existing blocks).
            result = notion_service.update_notion_page_matched(
                page_id=page_id,
                image_url=cloud_url,
                mark_prchi=mark_prchi,
                metadata=metadata
            )

            res_payload = {
                "success": True,
                "page_id": page_id,
                "prchi_marked": result.get("checkbox_updated", False),
                "image_appended": result.get("image_appended", False),
                "cloud_image_url": cloud_url,
                "notion_url": f"https://notion.so/{page_id.replace('-', '')}"
            }

            body = json.dumps(res_payload).encode('utf-8')
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
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
