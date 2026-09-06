import re
import difflib
from datetime import datetime

# Indian & Standard Words to Number dictionary
WORDS_MAP = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50,
    'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
    'hundred': 100, 'thousand': 1000, 'lakh': 100000, 'lakhs': 100000,
    'crore': 10000000, 'crores': 10000000
}

MONTHS_MAP = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2, 'mar': 3, 'march': 3,
    'apr': 4, 'april': 4, 'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'september': 9, 'sept': 9, 'oct': 10, 'october': 10,
    'nov': 11, 'november': 11, 'dec': 12, 'december': 12
}

HEADER_BLACKLIST = {
    'delivery', 'note', 'dated', 'date', 'mode', 'terms', 'dispatch',
    'reference', 'order', 'buyer', 'consignee', 'gstin', 'original',
    'duplicate', 'payment', 'destination', 'state', 'bank', 'declaration',
    'tax', 'invoice', 'bill', 'voucher'
}


def clean_ocr_text(text):
    """Normalize whitespace and standard OCR anomalies."""
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def parse_words_to_number(text):
    """
    Parses amount written in words, e.g.:
    'INR Ten Thousand One Hundred Thirty Only' -> 10130.0
    'INR Forty One Thousand Five Hundred Only' -> 41500.0
    """
    if not text:
        return None

    patterns = [
        r'(?:Amount Chargeable\s*\(in words\):?|Amount\s*in\s*words:?|words\)?[:.-]?|INR|Rupees|Rs\.?)\s*([A-Za-z\s]+?)(?:Only|\.|\n|$)',
        r'(?:INR|Rs\.?)\s+([A-Za-z\s]+?)\s+Only',
    ]

    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            raw_phrase = match.group(1)
            words = [w.lower() for w in re.findall(r'[a-zA-Z]+', raw_phrase)]
            total = 0
            current = 0
            found_any = False
            for w in words:
                if w in ['and', 'only', 'inr', 'rs', 'rupees', 'paise', 'paisa', 'amount', 'chargeable', 'for']:
                    continue
                if w in WORDS_MAP:
                    found_any = True
                    val = WORDS_MAP[w]
                    if val in [100, 1000, 100000, 10000000]:
                        if current == 0:
                            current = 1
                        current *= val
                        if val >= 1000:
                            total += current
                            current = 0
                    else:
                        current += val
            total += current
            if found_any and total > 0:
                return float(total)

    return None


def extract_date(text):
    """
    Extracts invoice date from voucher text and formats as standard YYYY-MM-DD.
    Handles:
    - 6-Sep-26, 06-Sep-2026, 6 Sep 2026, 6th Sep 2026
    - 06/09/2026, 06-09-2026, 06.09.2026
    - 2026-09-06
    """
    if not text:
        return ""

    # Priority 1: Check lines with "Dated" or "Date" keyword first
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines:
        if re.search(r'\b(?:Dated|Date|Dt\.?)\b', line, re.IGNORECASE):
            # Check for Day-MonthName-Year (e.g. 6-Sep-26 or 06-Sep-2026)
            m1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?[\s\/\-\.]([A-Za-z]{3,9})[\s\/\-\.](\d{2,4})\b', line)
            if m1:
                day = int(m1.group(1))
                mon = m1.group(2).lower()
                yr = int(m1.group(3))
                if yr < 100:
                    yr += 2000
                if mon in MONTHS_MAP and 1 <= day <= 31:
                    return f"{yr:04d}-{MONTHS_MAP[mon]:02d}-{day:02d}"

            # Check for DD/MM/YYYY or DD-MM-YYYY
            m2 = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](\d{2,4})\b', line)
            if m2:
                d = int(m2.group(1))
                m = int(m2.group(2))
                yr = int(m2.group(3))
                if yr < 100:
                    yr += 2000
                if 1 <= d <= 31 and 1 <= m <= 12 and 2000 <= yr <= 2099:
                    return f"{yr:04d}-{m:02d}-{d:02d}"

    # Priority 2: Anywhere in text for Day-MonthName-Year
    m_any1 = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)?[\s\/\-\.]([A-Za-z]{3,9})[\s\/\-\.](\d{2,4})\b', text)
    if m_any1:
        day = int(m_any1.group(1))
        mon = m_any1.group(2).lower()
        yr = int(m_any1.group(3))
        if yr < 100:
            yr += 2000
        if mon in MONTHS_MAP and 1 <= day <= 31:
            return f"{yr:04d}-{MONTHS_MAP[mon]:02d}-{day:02d}"

    # Priority 3: Anywhere in text for numeric DD/MM/YYYY
    m_any2 = re.search(r'\b(\d{1,2})[\/\-\.](\d{1,2})[\/\-\.](20\d{2})\b', text)
    if m_any2:
        d = int(m_any2.group(1))
        m = int(m_any2.group(2))
        yr = int(m_any2.group(3))
        if 1 <= d <= 31 and 1 <= m <= 12:
            return f"{yr:04d}-{m:02d}-{d:02d}"

    return ""


def extract_invoice_number(text, known_invoices=None):
    """
    Extracts invoice or voucher number using patterns tailored for Tally / GST Sales Invoices.
    Example formats: SM/26-27/1307, SM/26-27/C351, SM/26-27/1308, 1307, C350, etc.
    """
    if not text:
        return ""

    # 1. Check against known invoices from Notion database (HIGHEST ACCURACY)
    if known_invoices:
        text_clean = "".join(c for c in text if c.isalnum()).upper()
        for inv in known_invoices:
            if not inv:
                continue
            inv_clean = "".join(c for c in inv if c.isalnum()).upper()
            if inv_clean and inv_clean in text_clean:
                return inv
            if inv.lower() in text.lower():
                return inv

        # Lenient match for invoice suffix e.g. "1307" or "C351"
        for inv in known_invoices:
            parts = [p for p in re.split(r'[\/\-_]', inv) if p]
            if parts:
                suffix = parts[-1]
                if len(suffix) >= 3 and re.search(r'\b' + re.escape(suffix) + r'\b', text):
                    return inv

    # 2. Look for standard Tally series pattern e.g., "SM/26-27/1307" or "SM/26-27/C351"
    tally_patterns = [
        r'\b([A-Za-z]{1,6}\/\d{2}-\d{2}\/[A-Za-z0-9\-]+)\b',
        r'\b([A-Za-z0-9]+\/\d{4}-\d{2,4}\/[A-Za-z0-9\-]+)\b',
        r'\b([A-Za-z0-9]+-[A-Za-z0-9]+\/\d+)\b',
        r'\b([A-Za-z]{1,4}\/\d{2,4}\/[A-Za-z0-9]+)\b',
    ]

    for pat in tally_patterns:
        match = re.search(pat, text, re.IGNORECASE)
        if match:
            cand = match.group(1).strip()
            if cand.lower() not in HEADER_BLACKLIST:
                return cand

    # 3. Look for explicit keyword: "Invoice No", "Inv No", "Voucher No"
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for i, line in enumerate(lines):
        match = re.search(r'(?:Invoice\s*No\.?|Inv\s*No\.?|Voucher\s*No\.?|Bill\s*No\.?|Tax\s*Invoice\s*No\.?|Doc\s*No\.?)\s*[:.-]?\s*([A-Za-z0-9\/\-_]*)', line, re.IGNORECASE)
        if match:
            cand = match.group(1).strip(" .:,;-_")
            if cand and len(cand) >= 2 and cand.lower() not in HEADER_BLACKLIST:
                return cand
            if i + 1 < len(lines):
                next_tokens = lines[i + 1].split()
                if next_tokens:
                    next_cand = next_tokens[0].strip(" .:,;-_")
                    if len(next_cand) >= 2 and next_cand.lower() not in HEADER_BLACKLIST:
                        return next_cand

    return ""


def extract_amount(text, known_amounts=None):
    """
    Extracts total or invoice amount from voucher text.
    Handles Indian number formats, misread Rupee symbols, and Amount in Words.
    """
    if not text:
        return None

    # 1. First try parsing Amount in Words
    amt_from_words = parse_words_to_number(text)
    if amt_from_words is not None and amt_from_words > 0:
        return amt_from_words

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Keywords for total amount
    total_keywords = [
        r'(?:Grand\s*Total|Total\s*Amount|Net\s*Amount|Invoice\s*Total|Bill\s*Amount|Total\s*₹|Total\s*Rs\.?|Total\s*Value|Total)\s*[:.-]?\s*(?:[₹\?z2]|Rs\.?|INR)?\s*([0-9,]+(?:\.\d{1,2})?)',
        r'(?:₹|Rs\.?|INR)\s*([0-9,]+(?:\.\d{1,2})?)',
    ]

    candidate_amounts = []

    for line in lines:
        for pat in total_keywords:
            matches = re.finditer(pat, line, re.IGNORECASE)
            for m in matches:
                raw_amt = m.group(1).replace(',', '').strip()
                try:
                    val = float(raw_amt)
                    if val > 0 and val < 100000000:
                        is_grand_total = bool(re.search(r'grand\s*total|net\s*amount|total\s*amount|invoice\s*total', line, re.IGNORECASE))
                        candidate_amounts.append((val, 2 if is_grand_total else 1))
                except ValueError:
                    pass

    # Clean candidate amounts against known amounts
    if known_amounts:
        known_float_set = {float(a) for a in known_amounts if a is not None}
        for i, (val, prio) in enumerate(candidate_amounts):
            if val in known_float_set:
                return val
            str_val = str(int(val)) if val == int(val) else str(val)
            if str_val.startswith('2') and len(str_val) >= 3:
                try:
                    stripped = float(str_val[1:])
                    if stripped in known_float_set:
                        return stripped
                except ValueError:
                    pass

    if candidate_amounts:
        candidate_amounts.sort(key=lambda x: (x[1], x[0]), reverse=True)
        return candidate_amounts[0][0]

    # Fallback: scan for all numbers with 2 decimal places
    all_numbers = re.findall(r'\b([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.\d{2})|[0-9]+(?:\.\d{2}))\b', text)
    if all_numbers:
        vals = []
        for n in all_numbers:
            try:
                v = float(n.replace(',', ''))
                if v > 0 and v not in [2024.0, 2025.0, 2026.0, 2027.0]:
                    vals.append(v)
            except ValueError:
                pass
        if vals:
            if known_amounts:
                known_float_set = {float(a) for a in known_amounts if a is not None}
                for v in vals:
                    if v in known_float_set:
                        return v
            return max(vals)

    return None


def extract_customer_name(text, known_customers=None):
    """
    Extracts customer / party / buyer name from voucher text.
    Handles 'Buyer (Bill to)', 'Party Name', 'M/s', etc.
    """
    if not text:
        return ""

    if known_customers:
        best_known = ""
        highest_sim = 0.0
        text_lower = text.lower()

        for cust in known_customers:
            if not cust or len(cust) < 3:
                continue
            cust_lower = cust.lower()
            if cust_lower in text_lower:
                return cust
            for line in text.split('\n'):
                l_clean = line.strip().lower()
                sim = difflib.SequenceMatcher(None, cust_lower, l_clean).ratio()
                if sim > 0.75 and sim > highest_sim:
                    highest_sim = sim
                    best_known = cust

        if highest_sim > 0.75:
            return best_known

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    party_patterns = [
        r'(?:Party\s*Name|Buyer\s*\(Bill\s*to\)|Buyer|Consignee\s*\(Ship\s*to\)|Customer\s*Name|M\/s\.?|Messrs\.?|To\s*[:.-])\s*[:.-]?\s*([A-Za-z0-9\s&.,\'\(\)\-]+)',
    ]

    for i, line in enumerate(lines):
        for pat in party_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                cand = match.group(1).strip(" :.-,")
                if len(cand) >= 3 and not cand.lower().startswith(('gstin', 'address', 'state', 'state code', 'invoice', 'date')):
                    return cand
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip(" :.-,")
                    if len(next_line) >= 3 and not next_line.lower().startswith(('gstin', 'address', 'state', 'state code', 'invoice', 'date')):
                        return next_line

    ms_match = re.search(r'\bM\/[sS]\.?\s+([A-Za-z0-9\s&.,\'-]+)', text)
    if ms_match:
        return ("M/s " + ms_match.group(1).strip(" :.-,")).strip()

    return ""


def parse_voucher_text(text, known_customers=None, known_invoices=None, known_amounts=None):
    """
    Parses full OCR text and returns extracted structured fields:
    Invoice Number, Amount, Customer Name, and Date.
    """
    clean_text = clean_ocr_text(text)
    invoice_no = extract_invoice_number(clean_text, known_invoices)
    amount = extract_amount(clean_text, known_amounts)
    customer_name = extract_customer_name(clean_text, known_customers)
    date_str = extract_date(clean_text)

    return {
        "raw_text": clean_text,
        "invoice_no": invoice_no,
        "amount": amount,
        "customer_name": customer_name,
        "date": date_str,
        "has_extraction": bool(invoice_no or (amount is not None) or customer_name or date_str)
    }
