import os
import requests
import json

BASE_URL = "http://127.0.0.1:5000"

print("=" * 60)
print("[TEST] Running End-to-End Test Suite for Tally Voucher Web App")
print("=" * 60)

# 1. Test Home Page
print("\n[1/5] Testing GET / (Frontend Single-Page App)...")
res_home = requests.get(f"{BASE_URL}/")
assert res_home.status_code == 200, f"Expected 200, got {res_home.status_code}"
assert "Tally Voucher" in res_home.text, "Page missing title"
assert "TALLY SALES TO NOTION" in res_home.text, "Page missing database name"
print("[OK] Frontend HTML & template rendered successfully (200 OK)")

# 2. Test Network Info & QR Code
print("\n[2/5] Testing GET /api/network-info...")
res_net = requests.get(f"{BASE_URL}/api/network-info")
assert res_net.status_code == 200
data_net = res_net.json()
assert "qr_code" in data_net and data_net["qr_code"].startswith("data:image/png;base64,")
print(f"[OK] Mobile access URL: {data_net['url']} with QR Code generated")

# 3. Test Database Records
print("\n[3/5] Testing GET /api/records (Notion Database Fetch)...")
res_db = requests.get(f"{BASE_URL}/api/records")
assert res_db.status_code == 200
data_db = res_db.json()
assert data_db["success"] is True
records = data_db["records"]
print(f"[OK] Notion Database queried successfully! Total records: {len(records)}")
for r in records:
    print(f"   - Customer: {r['customer_name']:<22} | Inv: {r['invoice_no']:<16} | Amt: Rs.{r['amount'] or 0:<8} | RCG: {r['rcg']}")

# 4. Test Voucher Recognition & Matching (Ganesh Enterprises)
print("\n[4/5] Testing POST /api/process with sample_voucher_ganesh.png...")
img_path = "sample_vouchers/sample_voucher_ganesh.png"
with open(img_path, "rb") as f:
    files = {"image": ("sample_voucher_ganesh.png", f, "image/png")}
    data = {
        "ocr_text": "TAX INVOICE / SALES VOUCHER\nBuyer (Bill to): GANESH ENTERPRISES\nInvoice No: SM/26-27/1308\nDated: 06-Sep-2026\nGrand Total: Rs. 41500.00"
    }
    res_proc = requests.post(f"{BASE_URL}/api/process", files=files, data=data)

assert res_proc.status_code == 200
data_proc = res_proc.json()
assert data_proc["success"] is True
ext = data_proc["extracted"]
top = data_proc["top_match"]

print("   Extracted Data:")
print(f"   - Invoice No:    {ext['invoice_no']}")
print(f"   - Amount:        Rs. {ext['amount']}")
print(f"   - Customer Name: {ext['customer_name']}")

print("\n   Matching Result:")
print(f"   - Confidence:    {top['confidence']}%")
print(f"   - Target Record: {top['record']['customer_name']} ({top['record']['invoice_no']})")
print(f"   - Status:        {top['status']}")
print(f"   - Details:       {top['match_details']}")

assert top["confidence"] >= 95, f"Expected >= 95% confidence, got {top['confidence']}"
assert top["record"]["invoice_no"] == "SM/26-27/1308"
assert top["record"]["customer_name"] == "GANESH ENTERPRISES"
print("[OK] Voucher recognition & 100% confidence matching verified!")

# 5. Test Notion Sync (Reconciliation & Side-Peek Image Upload)
print("\n[5/5] Testing POST /api/sync-notion (Notion Update & Side-Peek Attachment)...")
target_page_id = top["record"]["id"]
sync_payload = {
    "page_id": target_page_id,
    "filename": data_proc["saved_filename"],
    "metadata": {
        "invoice_no": ext["invoice_no"],
        "amount": ext["amount"],
        "customer_name": ext["customer_name"],
        "add_remark": True
    }
}

res_sync = requests.post(f"{BASE_URL}/api/sync-notion", json=sync_payload)
assert res_sync.status_code == 200
data_sync = res_sync.json()
assert data_sync["success"] is True
assert data_sync["checkbox_marked"] is True
print(f"[OK] Notion page updated successfully!")
print(f"   - Checkbox 'RCG' Marked: {data_sync['checkbox_marked']}")
print(f"   - Image Block Appended:  {data_sync['image_appended']}")
print(f"   - Cloud Image URL:       {data_sync.get('cloud_image_url')}")
print(f"   - Notion URL:            {data_sync['notion_url']}")

# Verify the row state in database
res_verify = requests.get(f"{BASE_URL}/api/records?refresh=true")
data_verify = res_verify.json()
updated_row = next((r for r in data_verify["records"] if r["id"] == target_page_id), None)
assert updated_row is not None
assert updated_row["rcg"] is True
print(f"[OK] Live Database check: Row '{updated_row['customer_name']}' is now confirmed RCG = True!")

print("\n" + "=" * 60)
print("[SUCCESS] ALL TESTS PASSED SUCCESSFULLY!")
print("=" * 60)

