import sys
import os
import json
from http.server import BaseHTTPRequestHandler

root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import notion_service
import ocr_parser

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8')) if post_data else {}

            ocr_text = data.get('ocr_text', '')
            records = notion_service.query_database_records(filter_unreconciled=True, limit=300)

            # Build sets for OCR matching
            known_custs = {r["customer_name"] for r in records if r.get("customer_name")}
            known_custs.update({r["sites"] for r in records if r.get("sites")})
            known_amts = {r["price"] for r in records if r.get("price") is not None}

            extracted = ocr_parser.parse_prchi_text(
                ocr_text,
                known_customers=known_custs,
                known_amounts=known_amts
            )

            # Overrides
            if data.get('override_price') is not None:
                try:
                    extracted['price'] = float(data.get('override_price'))
                    extracted['amount'] = extracted['price']
                except ValueError:
                    pass
            elif data.get('override_amount') is not None:
                try:
                    extracted['price'] = float(data.get('override_amount'))
                    extracted['amount'] = extracted['price']
                except ValueError:
                    pass
            if data.get('override_customer'):
                extracted['customer_name'] = data.get('override_customer')
            if data.get('override_date'):
                extracted['date'] = data.get('override_date')

            matches = notion_service.match_voucher_with_records(extracted, records)
            top_match = matches[0] if matches else None

            res = {
                "success": True,
                "extracted": extracted,
                "top_match": top_match,
                "candidates": matches[:5],
                "total_pending": len(records)
            }

            body = json.dumps(res).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        except Exception as e:
            err = json.dumps({"success": False, "error": str(e)}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-Length', str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
