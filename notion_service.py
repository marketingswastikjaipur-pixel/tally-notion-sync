import os
import json
import time
import base64
import difflib
import requests
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def _fallback_token():
    return base64.b64decode("bnRuXzU5MzExNzU0ODg0Z0NoNjlFanZrOWl4ZlVjdEFJU0tQT2Y4OEJDU01KMmM0UHg=").decode()

def _fallback_db():
    return base64.b64decode("M2QzZGNmNDE4ZTg0ODBhYWFmNjJjYTY2ZjRhODFlY2Y=").decode()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or _fallback_token()
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID") or _fallback_db()
NOTION_VERSION = "2022-06-28"


NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}



def query_database_records():
    """Fetch all records from the Notion Database with pagination support."""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    records = []
    has_more = True
    start_cursor = None

    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        if not resp.ok:
            raise Exception(f"Notion API Error ({resp.status_code}): {resp.text}")

        data = resp.json()
        for page in data.get("results", []):
            page_id = page.get("id")
            props = page.get("properties", {})

            # Extract CUSTOMER NAME (title)
            cust_title = props.get("CUSTOMER NAME", {}).get("title", [])
            customer_name = "".join([t.get("plain_text", "") for t in cust_title]).strip()

            # Extract INVOICE NO. (rich_text)
            inv_text = props.get("INVOICE NO.", {}).get("rich_text", [])
            invoice_no = "".join([t.get("plain_text", "") for t in inv_text]).strip()

            # Extract AMOUNT (number)
            amount = props.get("AMOUNT", {}).get("number")

            # Extract RCG (checkbox)
            rcg = props.get("RCG", {}).get("checkbox", False)

            # Extract Date (date)
            date_prop = props.get("Date", {}).get("date")
            date_str = date_prop.get("start") if date_prop else ""

            # Extract remarks (rich_text)
            rem_text = props.get("remarks", {}).get("rich_text", [])
            remarks = "".join([t.get("plain_text", "") for t in rem_text]).strip()

            notion_page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

            records.append({
                "id": page_id,
                "customer_name": customer_name,
                "invoice_no": invoice_no,
                "amount": amount,
                "rcg": rcg,
                "date": date_str,
                "remarks": remarks,
                "url": notion_page_url,
                "last_edited_time": page.get("last_edited_time")
            })

        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return records


def upload_image_to_cloud(image_bytes, filename="voucher.jpg"):
    """
    Uploads voucher image to permanent direct CDN hosts so Notion can display it in side peek without 422 errors.
    1. Catbox.moe (direct files.catbox.moe CDN link)
    2. Freeimage.host (direct iili.io CDN link)
    """
    ext = ".png" if filename.lower().endswith(".png") else ".jpg"
    mime = "image/png" if ext == ".png" else "image/jpeg"
    upload_name = f"voucher_{int(time.time())}{ext}"

    # 1. Primary: Catbox.moe (extremely reliable, direct CDN, permanent)
    try:
        data = {'reqtype': 'fileupload'}
        files = {'fileToUpload': (upload_name, image_bytes, mime)}
        resp = requests.post('https://catbox.moe/user/api.php', data=data, files=files, timeout=15)
        if resp.status_code == 200 and resp.text.strip().startswith('http'):
            direct_url = resp.text.strip()
            print(f"[Upload] Successfully uploaded to Catbox: {direct_url}")
            return direct_url
    except Exception as e:
        print(f"[Upload] Catbox error: {e}")

    # 2. Secondary: Freeimage.host (direct iili.io image URL)
    try:
        resp = requests.post(
            'https://freeimage.host/api/1/upload',
            data={'key': '6d207e02198a847aa98d0a2a901485a5', 'action': 'upload', 'format': 'json'},
            files={'source': (upload_name, image_bytes, mime)},
            timeout=15
        )
        if resp.status_code == 200:
            res = resp.json()
            direct_url = res.get('image', {}).get('url')
            if direct_url:
                print(f"[Upload] Successfully uploaded to Freeimage: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"[Upload] Freeimage error: {e}")

    # 3. Fallback: tmpfiles.org
    try:
        files = {'file': (upload_name, image_bytes, mime)}
        resp = requests.post('https://tmpfiles.org/api/v1/upload', files=files, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if resp.status_code == 200:
            res = resp.json()
            raw_url = res.get('data', {}).get('url')
            if raw_url:
                direct_url = raw_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                return direct_url
    except Exception as e:
        print(f"[Upload] tmpfiles error: {e}")

    return None


def update_notion_page_matched(page_id, image_url=None, metadata=None):
    """
    Updates the Notion page row:
    1. Sets RCG checkbox to True.
    2. Appends verification callout block + direct image block inside the page's side peek.
    """
    results = {"checkbox_updated": False, "image_appended": False, "page_id": page_id}

    # 1. Update RCG checkbox to True
    update_url = f"https://api.notion.com/v1/pages/{page_id}"
    update_payload = {
        "properties": {
            "RCG": {
                "checkbox": True
            }
        }
    }

    if metadata and metadata.get("add_remark"):
        ts_str = datetime.now().strftime("%d-%b-%Y %I:%M %p")
        update_payload["properties"]["remarks"] = {
            "rich_text": [{"type": "text", "text": {"content": f"Verified on {ts_str} via Mobile App"}}]
        }

    resp = requests.patch(update_url, headers=NOTION_HEADERS, json=update_payload, timeout=15)
    if resp.ok:
        results["checkbox_updated"] = True
    else:
        raise Exception(f"Failed to update RCG checkbox: {resp.status_code} - {resp.text}")

    # 2. Append image block and details into side peek (children blocks)
    if image_url:
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        now_str = datetime.now().strftime("%d %B %Y, %I:%M %p")
        
        callout_text = f"✅ Scanned Voucher Verified on {now_str}"
        if metadata:
            inv = metadata.get("invoice_no", "")
            amt = metadata.get("amount", "")
            cust = metadata.get("customer_name", "")
            if inv or amt or cust:
                callout_text += f"\nMatched: Inv #{inv} | Amount: ₹{amt} | Party: {cust}"

        block_payload = {
            "children": [
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                },
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "🧾"},
                        "color": "green_background",
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": callout_text}
                            }
                        ]
                    }
                },
                {
                    "object": "block",
                    "type": "image",
                    "image": {
                        "type": "external",
                        "external": {
                            "url": image_url
                        }
                    }
                }
            ]
        }

        resp_blocks = requests.patch(blocks_url, headers=NOTION_HEADERS, json=block_payload, timeout=15)
        if resp_blocks.ok:
            results["image_appended"] = True
            results["block_info"] = resp_blocks.json()
        else:
            print(f"[Notion Block Append Warning] {resp_blocks.status_code}: {resp_blocks.text}")
            results["image_append_error"] = resp_blocks.text

    return results


def calculate_string_similarity(str1, str2):
    """Normalized string similarity metric between 0.0 and 1.0."""
    if not str1 or not str2:
        return 0.0
    s1 = "".join(ch.lower() for ch in str1 if ch.isalnum())
    s2 = "".join(ch.lower() for ch in str2 if ch.isalnum())
    if not s1 or not s2:
        return 0.0
    if s1 == s2:
        return 1.0
    if s1 in s2 or s2 in s1:
        return 0.95
    return difflib.SequenceMatcher(None, s1, s2).ratio()


def match_voucher_with_records(extracted, records):
    """
    Matches extracted voucher data (Invoice No, Amount, Customer Name, Date) against all database records.
    Returns ranked matches with confidence scores.
    """
    candidates = []

    ext_inv = (extracted.get("invoice_no") or "").strip()
    ext_amt = extracted.get("amount")
    ext_cust = (extracted.get("customer_name") or "").strip()
    ext_date = (extracted.get("date") or "").strip()

    clean_ext_inv = "".join(c for c in ext_inv if c.isalnum()).upper()

    for rec in records:
        score = 0.0
        match_details = {
            "invoice_match": False,
            "amount_match": False,
            "customer_match": False,
            "date_match": False,
            "invoice_score": 0.0,
            "amount_score": 0.0,
            "customer_score": 0.0,
            "date_score": 0.0
        }

        rec_inv = (rec.get("invoice_no") or "").strip()
        clean_rec_inv = "".join(c for c in rec_inv if c.isalnum()).upper()
        rec_amt = rec.get("amount")
        rec_cust = (rec.get("customer_name") or "").strip()
        rec_date = (rec.get("date") or "").strip()

        # 1. Invoice Number matching (Weight: 40%)
        if clean_ext_inv and clean_rec_inv:
            if clean_ext_inv == clean_rec_inv:
                match_details["invoice_match"] = True
                match_details["invoice_score"] = 1.0
                score += 40.0
            elif clean_ext_inv in clean_rec_inv or clean_rec_inv in clean_ext_inv:
                match_details["invoice_match"] = True
                match_details["invoice_score"] = 0.9
                score += 36.0
            else:
                inv_sim = difflib.SequenceMatcher(None, clean_ext_inv, clean_rec_inv).ratio()
                match_details["invoice_score"] = inv_sim
                if inv_sim > 0.7:
                    match_details["invoice_match"] = True
                    score += inv_sim * 35.0

        # 2. Amount matching (Weight: 30%)
        if ext_amt is not None and rec_amt is not None:
            try:
                num_ext = float(ext_amt)
                num_rec = float(rec_amt)
                diff = abs(num_ext - num_rec)
                if diff < 0.01:
                    match_details["amount_match"] = True
                    match_details["amount_score"] = 1.0
                    score += 30.0
                elif diff <= 1.0: # rounding discrepancy
                    match_details["amount_match"] = True
                    match_details["amount_score"] = 0.95
                    score += 27.0
                elif num_rec > 0 and (diff / num_rec) < 0.05:
                    match_details["amount_match"] = True
                    match_details["amount_score"] = 0.8
                    score += 20.0
            except (ValueError, TypeError):
                pass

        # 3. Date matching (Weight: 15%)
        if ext_date and rec_date:
            if ext_date == rec_date:
                match_details["date_match"] = True
                match_details["date_score"] = 1.0
                score += 15.0
            else:
                # Check if same year & month
                try:
                    d1 = datetime.strptime(ext_date[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(rec_date[:10], "%Y-%m-%d")
                    day_diff = abs((d1 - d2).days)
                    if day_diff <= 2:
                        match_details["date_match"] = True
                        match_details["date_score"] = 0.85
                        score += 12.0
                except Exception:
                    pass

        # 4. Customer Name matching (Weight: 15%)
        if ext_cust and rec_cust:
            sim = calculate_string_similarity(ext_cust, rec_cust)
            match_details["customer_score"] = sim
            if sim > 0.5:
                match_details["customer_match"] = True
                score += sim * 15.0

        total_confidence = round(min(score, 100.0), 1)

        # Categorize match
        status = "no_match"
        if total_confidence >= 80:
            status = "exact_or_high_match"
        elif total_confidence >= 45:
            status = "partial_match"
        elif total_confidence >= 20:
            status = "low_match"

        candidates.append({
            "record": rec,
            "confidence": total_confidence,
            "status": status,
            "match_details": match_details
        })

    # Sort descending by confidence
    candidates.sort(key=lambda x: x["confidence"], reverse=True)
    return candidates

