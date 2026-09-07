import os
import sys
import json

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

import notion_service
import ocr_parser
import app as flask_app

def test_ocr_parser():
    print("\n--- TEST 1: OCR Parser ---")
    sample_slip_text = """
    CASH MEMO / PRCHI
    Date: 07-Sep-2026
    Party Name: Baid ji a45 janta colony 9829012107
    Items: 2
    Total Price: 600.00
    Rupees Six Hundred Only
    """
    extracted = ocr_parser.parse_prchi_text(
        sample_slip_text,
        known_customers=["Baid ji a45 janta colony 9829012107", "MANJU KUMARI JI"],
        known_amounts=[600.0, 18200.0]
    )
    print("Extracted fields:", json.dumps(extracted, indent=2))
    assert extracted["date"] == "2026-09-07", f"Date mismatch: {extracted['date']}"
    assert extracted["price"] == 600.0, f"Price mismatch: {extracted['price']}"
    assert "Baid ji" in extracted["customer_name"], f"Customer mismatch: {extracted['customer_name']}"
    print("[SUCCESS] OCR Parser test passed!")


def test_notion_query_and_matching():
    print("\n--- TEST 2: Notion Query & 3-Field Matching ---")
    records = notion_service.query_database_records(filter_unreconciled=True, limit=50)
    print(f"Fetched {len(records)} pending records from Notion DB {notion_service.DATABASE_ID}.")
    assert len(records) > 0, "No records returned!"
    
    # Check that PRCHI is False for all
    for r in records:
        assert r["prchi"] is False, f"Found record with prchi != False: {r}"

    sample = records[0]
    print(f"Sample Record 1: Date={sample['date']}, Price={sample['price']}, Customer={sample['customer_name']}")

    # Create synthetic extracted voucher matching sample record
    extracted = {
        "date": sample["date"],
        "price": sample["price"],
        "amount": sample["price"],
        "customer_name": sample["customer_name"][:15] if sample["customer_name"] else "Sample Party"
    }

    candidates = notion_service.match_voucher_with_records(extracted, records)
    assert len(candidates) > 0, "No candidates returned!"
    top = candidates[0]
    print(f"Top match confidence: {top['confidence']}%")
    print(f"Match details: {top['match_details']}")
    print(f"Matched record ID: {top['record']['id']} (Target: {sample['id']})")
    assert top['record']['id'] == sample['id'], "Top match does not match target record!"
    assert top['confidence'] >= 75, f"Confidence too low: {top['confidence']}"
    print("[SUCCESS] Notion Query & Matching test passed!")


def test_flask_endpoints():
    print("\n--- TEST 3: Flask API Endpoints ---")
    client = flask_app.app.test_client()

    # 1. Test GET /api/records
    resp_records = client.get('/api/records')
    assert resp_records.status_code == 200
    data_records = resp_records.get_json()
    assert data_records["success"] is True
    print(f"GET /api/records returned {data_records['count']} pending records.")

    # 2. Test POST /api/process with OCR text
    payload = {
        "ocr_text": "Date: 2026-09-07\nTotal: 600\nParty: Baid ji"
    }
    resp_proc = client.post('/api/process', json=payload)
    assert resp_proc.status_code == 200
    data_proc = resp_proc.get_json()
    assert data_proc["success"] is True
    assert data_proc["extracted"]["date"] == "2026-09-07"
    assert data_proc["extracted"]["price"] == 600.0
    print("POST /api/process response top match:", data_proc.get("top_match", {}).get("confidence"))

    # 3. Test GET /api/mobile-qr
    resp_qr = client.get('/api/mobile-qr')
    assert resp_qr.status_code == 200
    data_qr = resp_qr.get_json()
    assert data_qr["success"] is True
    assert "mobile_url" in data_qr
    print(f"Mobile URL: {data_qr['mobile_url']}")
    print("[SUCCESS] Flask Endpoints test passed!")


if __name__ == "__main__":
    test_ocr_parser()
    test_notion_query_and_matching()
    test_flask_endpoints()
    print("\n*** ALL TESTS PASSED SUCCESSFULLY! ***")
