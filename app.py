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

# Load environment variables
load_dotenv()

import notion_service
import ocr_parser

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# On Vercel / serverless cloud, the root filesystem is read-only, use temp directory
if os.environ.get('VERCEL') or not os.access(BASE_DIR, os.W_OK):
    UPLOAD_DIR = os.path.join(tempfile.gettempdir(), 'uploads')
else:
    UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except Exception as e:
    print(f"Warning creating upload dir: {e}")

# Initialize Flask with explicit template & static folders for serverless runtimes
app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, 'templates'),
    static_folder=os.path.join(BASE_DIR, 'static')
)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024  # 32 MB max upload


# In-memory database cache for snappy matching
DB_CACHE = {
    "records": [],
    "last_fetched": 0,
    "known_customers": set(),
    "known_invoices": set(),
    "known_amounts": set()
}


def get_cached_records(force_refresh=False):
    """Fetch database records with 60-second in-memory caching."""
    now = time.time()
    if force_refresh or not DB_CACHE["records"] or (now - DB_CACHE["last_fetched"]) > 60:
        try:
            records = notion_service.query_database_records()
            DB_CACHE["records"] = records
            DB_CACHE["last_fetched"] = now
            DB_CACHE["known_customers"] = {r["customer_name"] for r in records if r.get("customer_name")}
            DB_CACHE["known_invoices"] = {r["invoice_no"] for r in records if r.get("invoice_no")}
            DB_CACHE["known_amounts"] = {r["amount"] for r in records if r.get("amount") is not None}
        except Exception as e:
            print(f"[Error fetching Notion records] {e}")
            if not DB_CACHE["records"]:
                raise e
    return DB_CACHE["records"]



def get_local_ip():
    """Detect local network IP for mobile device access."""
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
    """Get all records from Notion database."""
    force = request.args.get('refresh', 'false').lower() == 'true'
    try:
        records = get_cached_records(force_refresh=force)
        return jsonify({
            "success": True,
            "count": len(records),
            "reconciled_count": sum(1 for r in records if r.get("rcg")),
            "pending_count": sum(1 for r in records if not r.get("rcg")),
            "records": records,
            "database_id": notion_service.DATABASE_ID
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_voucher():
    """
    Processes OCR text and/or image upload, extracts fields, and matches with Notion rows.
    """
    try:
        ocr_text = ""
        saved_filename = None
        saved_image_url = None

        # Check if multipart form upload
        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                filename = f"voucher_{int(time.time()*1000)}_{secure_filename(file.filename)}"
                filepath = os.path.join(UPLOAD_DIR, filename)
                file.save(filepath)
                saved_filename = filename

        # Check for client-provided OCR text (from Tesseract.js in browser)
        if request.is_json:
            data = request.get_json()
            ocr_text = data.get('ocr_text', '')
            if data.get('image_base64'):
                # Save base64 image if provided
                b64_data = data.get('image_base64')
                if ',' in b64_data:
                    b64_data = b64_data.split(',', 1)[1]
                img_bytes = base64.b64decode(b64_data)
                filename = f"voucher_{int(time.time()*1000)}.jpg"
                filepath = os.path.join(UPLOAD_DIR, filename)
                with open(filepath, 'wb') as f:
                    f.write(img_bytes)
                saved_filename = filename
        else:
            ocr_text = request.form.get('ocr_text', '')

        # Fetch records
        records = get_cached_records()

        # Parse voucher text
        extracted = ocr_parser.parse_voucher_text(
            ocr_text,
            known_customers=DB_CACHE["known_customers"],
            known_invoices=DB_CACHE["known_invoices"],
            known_amounts=DB_CACHE["known_amounts"]
        )


        # Allow user manual overrides if passed in request
        if request.is_json:
            req_data = request.get_json()
            if req_data.get('override_invoice'):
                extracted['invoice_no'] = req_data.get('override_invoice')
            if req_data.get('override_amount') is not None:
                try:
                    extracted['amount'] = float(req_data.get('override_amount'))
                except ValueError:
                    pass
            if req_data.get('override_customer'):
                extracted['customer_name'] = req_data.get('override_customer')
            if req_data.get('override_date'):
                extracted['date'] = req_data.get('override_date')


        # Match against Notion records
        matches = notion_service.match_voucher_with_records(extracted, records)

        top_match = matches[0] if matches else None

        return jsonify({
            "success": True,
            "extracted": extracted,
            "saved_filename": saved_filename,
            "top_match": top_match,
            "candidates": matches[:5],
            "total_records": len(records)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/sync-notion', methods=['POST'])
def sync_notion():
    """
    Marks RCG checkbox as true in Notion and attaches the photo to the row's side peek.
    """
    try:
        data = request.get_json() or {}
        page_id = data.get('page_id')
        filename = data.get('filename')
        image_base64 = data.get('image_base64')
        metadata = data.get('metadata', {})

        if not page_id:
            return jsonify({"success": False, "error": "Missing page_id"}), 400

        image_bytes = None
        # Retrieve image bytes from filename or base64
        if filename:
            filepath = os.path.join(UPLOAD_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, 'rb') as f:
                    image_bytes = f.read()

        if not image_bytes and image_base64:
            if ',' in image_base64:
                image_base64 = image_base64.split(',', 1)[1]
            image_bytes = base64.b64decode(image_base64)

        # Upload image to public host for Notion block embedding
        cloud_url = None
        if image_bytes:
            cloud_url = notion_service.upload_image_to_cloud(image_bytes, filename or "voucher.jpg")

        # Update Notion row and append block
        result = notion_service.update_notion_page_matched(
            page_id=page_id,
            image_url=cloud_url,
            metadata=metadata
        )

        # Force refresh local cache so updated status appears immediately
        get_cached_records(force_refresh=True)

        return jsonify({
            "success": True,
            "page_id": page_id,
            "checkbox_marked": result.get("checkbox_updated", False),
            "image_appended": result.get("image_appended", False),
            "cloud_image_url": cloud_url,
            "notion_url": f"https://notion.so/{page_id.replace('-', '')}"
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/network-info', methods=['GET'])
def network_info():
    """Returns local IP and QR Code data URL for instant mobile connection."""
    port = 5000
    ip = get_local_ip()
    local_url = f"http://{ip}:{port}"

    # Generate QR Code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(local_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#10b981", back_color="#0f172a")

    buf = io.BytesIO()
    img.save(buf, format='PNG')
    qr_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')

    return jsonify({
        "local_ip": ip,
        "port": port,
        "url": local_url,
        "qr_code": qr_b64
    })


@app.route('/uploads/<path:filename>')
def serve_upload(filename):
    return send_from_directory(UPLOAD_DIR, filename)


if __name__ == '__main__':
    local_ip = get_local_ip()
    print("=" * 60)
    print(">> Tally Voucher Notion Sync Server Running!")
    print(f">> Local Access:   http://127.0.0.1:5000")
    print(f">> Mobile Access:  http://{local_ip}:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)

