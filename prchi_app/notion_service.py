import os
import json
import time
import base64
import difflib
import requests
from datetime import datetime
from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Load environment variables
load_dotenv(os.path.join(BASE_DIR, ".env"))

def _fallback_token():
    return base64.b64decode("bnRuXzU5MzExNzU0ODg0Z0NoNjlFanZrOWl4ZlVjdEFJU0tQT2Y4OEJDU01KMmM0UHg=").decode()

NOTION_TOKEN = os.environ.get("NOTION_TOKEN") or _fallback_token()
DATABASE_ID = os.environ.get("NOTION_DATABASE_ID") or "f6d358b9623f4b32b0cf4969cb6ebf35"
CUSTOMER_DATABASE_ID = os.environ.get("CUSTOMER_DATABASE_ID") or "b86dc86e-4b00-4061-a1b0-0845e8b86366"
NOTION_VERSION = "2022-06-28"

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

# In-memory customer mapping cache: {customer_page_id: customer_name}
CUSTOMER_CACHE = {}

def load_customer_cache():
    """Loads bundled customer cache from JSON file into memory."""
    global CUSTOMER_CACHE
    cache_path = os.path.join(BASE_DIR, "customer_cache.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                CUSTOMER_CACHE = json.load(f)
            print(f"[NotionService] Loaded {len(CUSTOMER_CACHE)} customers from local cache.")
        except Exception as e:
            print(f"[NotionService] Error loading local customer cache: {e}")

# Initial load on import
load_customer_cache()

def resolve_customer_name(cust_id):
    """
    Resolves customer page ID to plain customer name.
    Uses memory cache first, then fetches on-demand from Notion if unknown.
    """
    if not cust_id:
        return ""
    if cust_id in CUSTOMER_CACHE:
        return CUSTOMER_CACHE[cust_id]
    
    # Fetch from Notion directly
    try:
        url = f"https://api.notion.com/v1/pages/{cust_id}"
        resp = requests.get(url, headers=NOTION_HEADERS, timeout=8)
        if resp.ok:
            data = resp.json()
            title_objs = data.get("properties", {}).get("Name", {}).get("title", [])
            name = "".join([t.get("plain_text", "") for t in title_objs]).strip()
            CUSTOMER_CACHE[cust_id] = name
            return name
    except Exception as e:
        print(f"[NotionService] Error fetching customer {cust_id}: {e}")
    
    return ""


def query_database_records(filter_unreconciled=True, limit=250):
    """
    Fetches records from the target Notion database (f6d358b9623f4b32b0cf4969cb6ebf35).
    - Sorts by Date descending so the latest records appear first.
    - If filter_unreconciled is True, filters where PRCHI checkbox is False.
    - Resolves customer relation names.
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    records = []
    has_more = True
    start_cursor = None
    fetched_count = 0

    payload = {
        "sorts": [
            {"property": "Date", "direction": "descending"}
        ]
    }
    if filter_unreconciled:
        payload["filter"] = {
            "property": "PRCHI",
            "checkbox": {"equals": False}
        }

    while has_more and fetched_count < limit:
        batch_size = min(100, limit - fetched_count)
        payload["page_size"] = batch_size
        if start_cursor:
            payload["start_cursor"] = start_cursor

        resp = requests.post(url, headers=NOTION_HEADERS, json=payload, timeout=15)
        if not resp.ok:
            raise Exception(f"Notion API Error ({resp.status_code}): {resp.text}")

        data = resp.json()
        results = data.get("results", [])
        for page in results:
            page_id = page.get("id")
            props = page.get("properties", {})

            # 1. PRCHI checkbox
            prchi = props.get("PRCHI", {}).get("checkbox", False)

            # 2. Date
            date_prop = props.get("Date", {}).get("date")
            date_str = date_prop.get("start") if date_prop else ""

            # 3. Price (final amount)
            price = props.get("Price", {}).get("number")

            # 4. Sites (title property)
            sites_objs = props.get("sites", {}).get("title", [])
            sites = "".join([t.get("plain_text", "") for t in sites_objs]).strip()

            # 5. Customer Name (relation)
            cust_rel = props.get("customer  name", {}).get("relation", [])
            customer_name = ""
            if cust_rel:
                cust_id = cust_rel[0].get("id")
                customer_name = resolve_customer_name(cust_id)
            
            # If relation customer name is empty, use sites as customer / party name
            display_customer = customer_name if customer_name else sites

            # Extra info for context
            rate = props.get("RATE", {}).get("number")
            qty = props.get("QTY", {}).get("number")

            notion_page_url = page.get("url", f"https://notion.so/{page_id.replace('-', '')}")

            records.append({
                "id": page_id,
                "customer_name": display_customer,
                "raw_customer_name": customer_name,
                "sites": sites,
                "price": price,
                "amount": price,  # Alias for matching convenience
                "date": date_str,
                "prchi": prchi,
                "rate": rate,
                "qty": qty,
                "url": notion_page_url,
                "last_edited_time": page.get("last_edited_time")
            })

        fetched_count += len(results)
        has_more = data.get("has_more", False)
        start_cursor = data.get("next_cursor")

    return records


def get_database_stats():
    """
    Returns quick stats for dashboard:
    - total pending (PRCHI = False)
    - recently reconciled count
    """
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    
    # 1. Pending count (PRCHI = False)
    pending_payload = {
        "filter": {"property": "PRCHI", "checkbox": {"equals": False}},
        "page_size": 1
    }
    # 2. Reconciled count (PRCHI = True)
    reconciled_payload = {
        "filter": {"property": "PRCHI", "checkbox": {"equals": True}},
        "page_size": 1
    }
    
    stats = {"pending": 0, "reconciled": 0, "total": 0}
    try:
        r1 = requests.post(url, headers=NOTION_HEADERS, json=pending_payload, timeout=8).json()
        stats["pending"] = len(r1.get("results", []))  # At least active
        r2 = requests.post(url, headers=NOTION_HEADERS, json=reconciled_payload, timeout=8).json()
        stats["reconciled"] = len(r2.get("results", []))
    except Exception as e:
        print(f"[NotionService] Error getting stats: {e}")
        
    return stats


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
    Matches extracted voucher data against database records.
    CRITERIA:
    - ONLY records where PRCHI is NOT True (prchi == False) can be considered.
    - Matching fields:
      1. Date (Weight: 35%)
      2. Price / Final Amount (Weight: 35%)
      3. Customer Name / Sites (Weight: 30%)
    Returns sorted candidate matches with confidence scores.
    """
    candidates = []

    ext_amt = extracted.get("amount") if extracted.get("amount") is not None else extracted.get("price")
    ext_cust = (extracted.get("customer_name") or "").strip()
    ext_date = (extracted.get("date") or "").strip()

    # Filter: ONLY consider records where PRCHI checkbox is False
    valid_records = [r for r in records if not r.get("prchi")]

    for rec in valid_records:
        score = 0.0
        match_details = {
            "date_match": False,
            "date_score": 0.0,
            "price_match": False,
            "price_score": 0.0,
            "customer_match": False,
            "customer_score": 0.0
        }

        rec_amt = rec.get("price")
        rec_cust = (rec.get("customer_name") or "").strip()
        rec_sites = (rec.get("sites") or "").strip()
        rec_date = (rec.get("date") or "").strip()

        # 1. Date matching (Weight: 35%)
        if ext_date and rec_date:
            if ext_date == rec_date:
                match_details["date_match"] = True
                match_details["date_score"] = 1.0
                score += 35.0
            else:
                try:
                    d1 = datetime.strptime(ext_date[:10], "%Y-%m-%d")
                    d2 = datetime.strptime(rec_date[:10], "%Y-%m-%d")
                    day_diff = abs((d1 - d2).days)
                    if day_diff == 1:
                        match_details["date_match"] = True
                        match_details["date_score"] = 0.90
                        score += 31.5
                    elif day_diff <= 3:
                        match_details["date_match"] = True
                        match_details["date_score"] = 0.75
                        score += 26.0
                    elif d1.year == d2.year and d1.month == d2.month:
                        match_details["date_score"] = 0.50
                        score += 17.5
                except Exception:
                    pass

        # 2. Price / Final Amount matching (Weight: 35%)
        if ext_amt is not None and rec_amt is not None:
            try:
                num_ext = float(ext_amt)
                num_rec = float(rec_amt)
                diff = abs(num_ext - num_rec)
                if diff < 0.01:
                    match_details["price_match"] = True
                    match_details["price_score"] = 1.0
                    score += 35.0
                elif diff <= 1.0:  # Rounding discrepancy
                    match_details["price_match"] = True
                    match_details["price_score"] = 0.95
                    score += 33.0
                elif num_rec > 0 and (diff / num_rec) <= 0.05:  # within 5%
                    match_details["price_match"] = True
                    match_details["price_score"] = 0.80
                    score += 28.0
                elif num_rec > 0 and (diff / num_rec) <= 0.10:  # within 10%
                    match_details["price_score"] = 0.50
                    score += 17.5
            except (ValueError, TypeError):
                pass

        # 3. Customer Name / Sites matching (Weight: 30%)
        if ext_cust:
            # Check against relation customer name
            sim_cust = calculate_string_similarity(ext_cust, rec_cust)
            # Check against sites title text as well
            sim_sites = calculate_string_similarity(ext_cust, rec_sites) if rec_sites else 0.0
            best_cust_sim = max(sim_cust, sim_sites)

            # Token overlap check (e.g. "Suresh Batra" inside "Suresh Batra Ji Flat 201")
            ext_tokens = [t.lower() for t in ext_cust.split() if len(t) >= 3]
            target_text = (rec_cust + " " + rec_sites).lower()
            token_matches = sum(1 for t in ext_tokens if t in target_text)
            if ext_tokens and (token_matches / len(ext_tokens)) >= 0.7:
                best_cust_sim = max(best_cust_sim, 0.95)

            match_details["customer_score"] = round(best_cust_sim, 2)
            if best_cust_sim >= 0.5:
                match_details["customer_match"] = True
                score += best_cust_sim * 30.0

        total_confidence = round(min(score, 100.0), 1)

        # Categorize match
        status = "no_match"
        if total_confidence >= 75:
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


def upload_image_to_cloud(image_bytes, filename="prchi_voucher.jpg"):
    """
    Uploads voucher image to permanent direct CDN hosts so Notion displays it inside side peek without 422 errors.
    Hosts: Catbox.moe -> Freeimage.host -> tmpfiles.org
    """
    ext = ".png" if filename.lower().endswith(".png") else ".jpg"
    mime = "image/png" if ext == ".png" else "image/jpeg"
    upload_name = f"prchi_{int(time.time())}{ext}"

    # 1. Catbox.moe
    try:
        data = {'reqtype': 'fileupload'}
        files = {'fileToUpload': (upload_name, image_bytes, mime)}
        resp = requests.post('https://catbox.moe/user/api.php', data=data, files=files, timeout=15)
        if resp.status_code == 200 and resp.text.strip().startswith('http'):
            direct_url = resp.text.strip()
            print(f"[Upload] Catbox success: {direct_url}")
            return direct_url
    except Exception as e:
        print(f"[Upload] Catbox error: {e}")

    # 2. Freeimage.host
    try:
        resp = requests.post(
            'https://freeimage.host/api/1/upload',
            data={'key': '6d207e02198a847aa98d0a2a901485a5', 'action': 'upload', 'format': 'json'},
            files={'source': (upload_name, image_bytes, mime)},
            timeout=15
        )
        if resp.status_code == 200:
            direct_url = resp.json().get('image', {}).get('url')
            if direct_url:
                print(f"[Upload] Freeimage success: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"[Upload] Freeimage error: {e}")

    # 3. Fallback: tmpfiles.org
    try:
        files = {'file': (upload_name, image_bytes, mime)}
        resp = requests.post('https://tmpfiles.org/api/v1/upload', files=files, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12)
        if resp.status_code == 200:
            raw_url = resp.json().get('data', {}).get('url')
            if raw_url:
                direct_url = raw_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                return direct_url
    except Exception as e:
        print(f"[Upload] tmpfiles error: {e}")

    return None


def update_notion_page_matched(page_id, image_url=None, mark_prchi=True, metadata=None):
    """
    Updates the Notion page row:
    1. Sets PRCHI checkbox to True (if mark_prchi is True).
       CRITICAL: REMARKS and all other column properties are left 100% UNTOUCHED.
    2. Appends verification callout block + direct image block inside the page's side peek.
       Existing blocks (images, text) inside side peek are preserved completely.
    """
    results = {"checkbox_updated": False, "image_appended": False, "page_id": page_id}

    # 1. Update PRCHI checkbox (ONLY PRCHI checkbox, NOTHING ELSE)
    if mark_prchi:
        update_url = f"https://api.notion.com/v1/pages/{page_id}"
        update_payload = {
            "properties": {
                "PRCHI": {
                    "checkbox": True
                }
            }
        }
        resp = requests.patch(update_url, headers=NOTION_HEADERS, json=update_payload, timeout=15)
        if resp.ok:
            results["checkbox_updated"] = True
            print(f"[NotionService] Marked PRCHI: True for page {page_id}")
        else:
            raise Exception(f"Failed to update PRCHI checkbox: {resp.status_code} - {resp.text}")

    # 2. Append image block and details into side peek (children blocks)
    # Existing blocks are NOT replaced; new blocks are appended to the end of the page body.
    if image_url:
        blocks_url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        now_str = datetime.now().strftime("%d %B %Y, %I:%M %p")

        callout_text = f"✅ Prchi Voucher Verified on {now_str}"
        if metadata:
            amt = metadata.get("amount") or metadata.get("price", "")
            cust = metadata.get("customer_name", "")
            dt = metadata.get("date", "")
            details = []
            if dt:
                details.append(f"Date: {dt}")
            if amt:
                details.append(f"Price: ₹{amt}")
            if cust:
                details.append(f"Party: {cust}")
            if details:
                callout_text += "\n" + " | ".join(details)

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
                        "color": "blue_background",
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
            print(f"[NotionService] Successfully appended voucher image into side peek for page {page_id}")
        else:
            print(f"[Notion Block Append Warning] {resp_blocks.status_code}: {resp_blocks.text}")
            results["image_append_error"] = resp_blocks.text

    return results
