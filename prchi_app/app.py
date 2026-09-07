import os
import io
import time
import socket
import base64
import tempfile
import qrcode
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

import notion_service
import ocr_parser

# Serverless / Vercel friendly temp uploads dir
if os.environ.get('VERCEL') or not os.access(BASE_DIR, os.W_OK):
    UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'prchi_uploads')
else:
    UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning creating upload dir: {e}")

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB max upload

# Database in-memory cache for fast responsive matching
DB_CACHE = {
    "records": [],
    "last_fetched": 0,
    "known_customers": set(),
    "known_amounts": set(),
}


def get_cached_records(force_refresh=False):
    """Fetches database records with 60s memory caching."""
    now = time.time()
    if force_refresh or not DB_CACHE["records"] or (now - DB_CACHE["last_fetched"]) > 60:
        try:
            records = notion_service.query_database_records(filter_unreconciled=True, limit=300)
            DB_CACHE["records"] = records
            DB_CACHE["last_fetched"] = now
            
            # Populate known customers
            cust_set = {r["customer_name"] for r in records if r.get("customer_name")}
            cust_set.update({r["sites"] for r in records if r.get("sites")})
            DB_CACHE["known_customers"] = cust_set
            
            # Populate known amounts
            DB_CACHE["known_amounts"] = {r["price"] for r in records if r.get("price") is not None}
            print(f"[App] Cached {len(records)} pending PRCHI records.")
        except Exception as e:
            print(f"[App Error fetching records] {e}")
            if not DB_CACHE["records"]:
                raise e
    return DB_CACHE["records"]


def get_local_ip():
    """Detect local IP for mobile camera access over local Wi-Fi."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.route('/')
@app.route('/api/index')
@app.route('/api/index.py')
def index():
    return render_template('index.html')


@app.route('/static/<path:filename>')
def custom_static(filename):
    static_dir = os.path.join(BASE_DIR, 'static')
    return send_from_directory(static_dir, filename)


@app.route('/api/records', methods=['GET'])
def get_records():
    """Returns pending PRCHI records from Notion database."""
    force = request.args.get('refresh', 'false').lower() == 'true'
    try:
        records = get_cached_records(force_refresh=force)
        return jsonify({
            "success": True,
            "count": len(records),
            "pending_count": len(records),
            "records": records,
            "database_id": notion_service.DATABASE_ID
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_prchi():
    """
    Processes OCR text / image upload, extracts Date, Customer Name, and Price,
    and returns ranked matching candidates where PRCHI is False.
    """
    try:
        ocr_text = ""
        saved_filename = None

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = f"prchi_{int(time.time()*1000)}_{secure_filename(file.filename)}"
                filepath = os.path.join(UPLOAD_DIR, filename)
                file.save(filepath)
                saved_filename = filename

        if request.is_json:
            data = request.get_json()
            ocr_text = data.get('ocr_text', '')
            if data.get('image_base64'):
                b64_data = data.get('image_base64')
                if ',' in b64_data:
                    b64_data = b64_data.split(',', 1)[1]
                img_bytes = base64.b64decode(b64_data)
                filename = f"prchi_{int(time.time()*1000)}.jpg"
                filepath = os.path.join(UPLOAD_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                saved_filename = filename
        else:
            ocr_text = request.form.get('ocr_text', '')

        # Fetch pending records
        records = get_cached_records()

        # Parse prchi slip text
        extracted = ocr_parser.parse_prchi_text(
            ocr_text,
            known_customers=DB_CACHE["known_customers"],
            known_amounts=DB_CACHE["known_amounts"]
        )

        # Allow user manual overrides
        if request.is_json:
            req_data = request.get_json()
            if req_data.get('override_price') is not None:
                try:
                    extracted['price'] = float(req_data.get('override_price'))
                    extracted['amount'] = extracted['price']
                except ValueError:
                    pass
            elif req_data.get('override_amount') is not None:
                try:
                    extracted['price'] = float(req_data.get('override_amount'))
                    extracted['amount'] = extracted['price']
                except ValueError:
                    pass
            if req_data.get('override_customer'):
                extracted['customer_name'] = req_data.get('override_customer')
            if req_data.get('override_date'):
                extracted['date'] = req_data.get('override_date')

        # Match against Notion records (only PRCHI == False records considered)
        matches = notion_service.match_voucher_with_records(extracted, records)
        top_match = matches[0] if matches else None

        return jsonify({
            "success": True,
            "extracted": extracted,
            "saved_filename": saved_filename,
            "top_match": top_match,
            "candidates": matches[:5],
            "total_pending": len(records)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sync-notion', methods=['POST'])
def sync_notion():
    """
    Reconciles voucher:
    1. Sets PRCHI checkbox to True (if mark_prchi is True).
       Leaves remarks and all other columns completely untouched.
    2. Appends image to the side peek blocks (preserving existing blocks).
    """
    try:
        data = request.get_json() or {}
        page_id = data.get('page_id')
        filename = data.get('filename')
        image_base64 = data.get('image_base64')
        metadata = data.get('metadata', {})
        mark_prchi = data.get('mark_prchi', True)

        if not page_id:
            return jsonify({"success": False, "error": "Missing page_id"}), 400

        image_bytes = None
        if filename:
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    image_bytes = f.read()

        if not image_bytes and image_base64:
            if ',' in image_base64:
                image_base64 = image_base64.split(',', 1)[1]
            image_bytes = base64.b64decode(image_base64)

        # Upload image to CDN for Notion embedding
        cloud_url = None
        if image_bytes:
            cloud_url = notion_service.upload_image_to_cloud(image_bytes, filename or "prchi_voucher.jpg")

        # Update Notion row (marks PRCHI checkbox: True, appends side peek block, touches NO remarks or other columns)
        result = notion_service.update_notion_page_matched(
            page_id=page_id,
            image_url=cloud_url,
            mark_prchi=mark_prchi,
            metadata=metadata
        )

        # Invalidate local cache so reconciled item is removed from pending list immediately
        get_cached_records(force_refresh=True)

        return jsonify({
            "success": True,
            "page_id": page_id,
            "prchi_marked": result.get("checkbox_updated", False),
            "image_appended": result.get("image_appended", False),
            "cloud_image_url": cloud_url,
            "notion_url": f"https://notion.so/{page_id.replace('-', '')}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/mobile-qr', methods=['GET'])
def get_mobile_qr():
    """Generates QR code for opening app on mobile device on same local network."""
    port = int(os.environ.get("PORT", 5001))
    local_ip = get_local_ip()
    mobile_url = f"http://{local_ip}:{port}"

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(mobile_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')

    return jsonify({
        "success": True,
        "mobile_url": mobile_url,
        "qr_base64": f"data:image/png;base64,{qr_b64}",
        "local_ip": local_ip,
        "port": port
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    local_ip = get_local_ip()
    print("=================================================================")
    print("  PRCHI VOUCHER NOTION SYNC APP STARTED")
    print(f"  Local Web App:     http://localhost:{port}")
    print(f"  Mobile Phone URL:  http://{local_ip}:{port}")
    print(f"  Notion Database:   {notion_service.DATABASE_ID}")
    print("=================================================================")
    app.run(host='0.0.0.0', port=port, debug=False)
