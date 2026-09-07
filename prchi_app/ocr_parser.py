import re
import difflib
from datetime import datetime

# Number words dictionary
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

BLACKLIST_WORDS = {
    'total', 'amount', 'date', 'dated', 'qty', 'rate', 'price', 'gstin',
    'address', 'state', 'signature', 'authorised', 'subtotal', 'cgst',
    'sgst', 'igst', 'rupees', 'inr', 'prchi', 'challan', 'slip', 'cash'
}


def clean_ocr_text(text):
    """Normalize line endings and whitespace."""
    if not text:
        return ""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'[ \t]+', ' ', text)
    return text.strip()


def parse_words_to_number(text):
    """Parses amount in words, e.g. 'Rupees Six Hundred Only' -> 600.0."""
    if not text:
        return None

    patterns = [
        r'(?:Amount\s*in\s*words:?|Amount:?|INR|Rupees|Rs\.?)\s*([A-Za-z\s]+?)(?:Only|\.|\n|$)',
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
                if w in ['and', 'only', 'inr', 'rs', 'rupees', 'paise', 'paisa', 'amount', 'for']:
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
    Extracts date from voucher slip and normalizes to standard YYYY-MM-DD string.
    Supports:
    - 07/09/2026, 7/9/26, 7-9-2026, 07-09-26, 07.09.2026
    - 7-Sep-2026, 07-Sep-26, 7 Sep 2026, 7th Sep 2026
    - 2026-09-07
    """
    if not text:
        return ""

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Priority 1: Check lines explicitly labeled with "Date" or "Dated" or "Dt"
    for line in lines:
        if re.search(r'\b(?:Dated|Date|Dt\.?)\b', line, re.IGNORECASE):
            # Alpha month: 7-Sep-26, 07-Sep-2026, 7 Sep 26
            m_alpha = re.search(r'\b(\d{1,2})[-/\s.]([A-Za-z]{3,9})[-/\s.](\d{2,4})\b', line)
            if m_alpha:
                d = int(m_alpha.group(1))
                m_str = m_alpha.group(2).lower()[:3]
                yr = int(m_alpha.group(3))
                if yr < 100:
                    yr += 2000
                if m_str in MONTHS_MAP and 1 <= d <= 31:
                    return f"{yr:04d}-{MONTHS_MAP[m_str]:02d}-{d:02d}"

            # Numeric: 07/09/2026 or 07-09-26
            m_num = re.search(r'\b(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})\b', line)
            if m_num:
                d = int(m_num.group(1))
                m = int(m_num.group(2))
                yr = int(m_num.group(3))
                if yr < 100:
                    yr += 2000
                if 1 <= d <= 31 and 1 <= m <= 12:
                    return f"{yr:04d}-{m:02d}-{d:02d}"

    # Priority 2: General text scan for alpha month: e.g. 7-Sep-2026 or 07-Sep-26
    m_alpha_gen = re.search(r'\b(\d{1,2})[-/\s.]([A-Za-z]{3,9})[-/\s.](\d{2,4})\b', text)
    if m_alpha_gen:
        d = int(m_alpha_gen.group(1))
        m_str = m_alpha_gen.group(2).lower()[:3]
        yr = int(m_alpha_gen.group(3))
        if yr < 100:
            yr += 2000
        if m_str in MONTHS_MAP and 1 <= d <= 31:
            return f"{yr:04d}-{MONTHS_MAP[m_str]:02d}-{d:02d}"

    # Priority 3: General scan for ISO format: 2026-09-07
    m_iso = re.search(r'\b(20\d{2})[-/.](0?[1-9]|1[0-2])[-/.](0?[1-9]|[12]\d|3[01])\b', text)
    if m_iso:
        return f"{int(m_iso.group(1)):04d}-{int(m_iso.group(2)):02d}-{int(m_iso.group(3)):02d}"

    # Priority 4: Standard Indian DD-MM-YYYY or DD/MM/YY
    m_num_gen = re.findall(r'\b(\d{1,2})[-/. ](\d{1,2})[-/. ](\d{2,4})\b', text)
    for (d_str, m_str, y_str) in m_num_gen:
        d = int(d_str)
        m = int(m_str)
        yr = int(y_str)
        if yr < 100:
            yr += 2000
        if 2020 <= yr <= 2035 and 1 <= m <= 12 and 1 <= d <= 31:
            return f"{yr:04d}-{m:02d}-{d:02d}"

    return ""


def extract_price(text, known_amounts=None):
    """
    Extracts total price or final amount from slip text.
    Handles Indian number formats, misread Rupee symbols, and known pending database amounts.
    """
    if not text:
        return None

    # 1. Check Amount in words first
    amt_words = parse_words_to_number(text)
    if amt_words and amt_words > 0:
        return amt_words

    lines = [l.strip() for l in text.split('\n') if l.strip()]

    # Keywords for final price
    price_keywords = [
        r'(?:Grand\s*Total|Total\s*Price|Final\s*Amount|Net\s*Amount|Total\s*Amount|Total\s*₹|Total\s*Rs\.?|Price|Total)\s*[:.-]?\s*(?:[₹\?z2]|Rs\.?|INR)?\s*([0-9,]+(?:\.\d{1,2})?)',
        r'(?:₹|Rs\.?|INR)\s*([0-9,]+(?:\.\d{1,2})?)',
    ]

    candidate_amounts = []

    for line in lines:
        for pat in price_keywords:
            matches = re.finditer(pat, line, re.IGNORECASE)
            for m in matches:
                raw_amt = m.group(1).replace(',', '').strip()
                try:
                    val = float(raw_amt)
                    if 0 < val < 100000000:
                        is_grand_total = bool(re.search(r'grand\s*total|final|net\s*amount|total\s*price|total\s*amount', line, re.IGNORECASE))
                        candidate_amounts.append((val, 2 if is_grand_total else 1))
                except ValueError:
                    pass

    # If known pending amounts provided from Notion DB, verify against them
    if known_amounts:
        known_float_set = {float(a) for a in known_amounts if a is not None}
        for (val, prio) in candidate_amounts:
            if val in known_float_set:
                return val
            # Handle OCR leading '2' for ₹ symbol e.g. 2600 -> 600
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

    # Fallback: scan for all valid numbers with decimal places or larger integers
    all_numbers = re.findall(r'\b([0-9]{1,3}(?:,[0-9]{2,3})*(?:\.\d{2})|[0-9]+(?:\.\d{2})?)\b', text)
    if all_numbers:
        vals = []
        for n in all_numbers:
            try:
                v = float(n.replace(',', ''))
                # Exclude obvious year numbers
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
    Extracts customer / party name from slip text.
    Uses known customer list for high-accuracy direct / fuzzy matches.
    """
    if not text:
        return ""

    text_lower = text.lower()

    # 1. Match against known customers from the database (HIGHEST ACCURACY)
    if known_customers:
        best_known = ""
        highest_score = 0.0

        for cust in known_customers:
            if not cust or len(cust) < 3:
                continue
            cust_lower = cust.lower()
            
            # Exact substring
            if cust_lower in text_lower:
                return cust
            
            # Multi-word token overlap
            cust_words = [w for w in cust_lower.split() if len(w) >= 3 and w not in BLACKLIST_WORDS]
            if len(cust_words) >= 2:
                matched_words = sum(1 for w in cust_words if w in text_lower)
                ratio = matched_words / len(cust_words)
                if ratio >= 0.75 and ratio > highest_score:
                    highest_score = ratio
                    best_known = cust

            # Fuzzy line comparison
            for line in text.split('\n'):
                line_clean = line.strip().lower()
                sim = difflib.SequenceMatcher(None, cust_lower, line_clean).ratio()
                if sim > 0.75 and sim > highest_score:
                    highest_score = sim
                    best_known = cust

        if highest_score >= 0.70:
            return best_known

    # 2. Heuristic extraction from labeled party / buyer lines
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    party_patterns = [
        r'(?:Party\s*Name|Customer\s*Name|Buyer|M\/s\.?|Messrs\.?|Name|To|Site)\s*[:.-]?\s*([A-Za-z0-9\s&.,\'\(\)\-]+)',
    ]

    for i, line in enumerate(lines):
        for pat in party_patterns:
            match = re.search(pat, line, re.IGNORECASE)
            if match:
                cand = match.group(1).strip(" :.-,")
                if len(cand) >= 3 and cand.lower() not in BLACKLIST_WORDS:
                    return cand
                if i + 1 < len(lines):
                    next_cand = lines[i + 1].strip(" :.-,")
                    if len(next_cand) >= 3 and next_cand.lower() not in BLACKLIST_WORDS:
                        return next_cand

    # Check for M/s prefix anywhere
    ms_match = re.search(r'\bM\/[sS]\.?\s+([A-Za-z0-9\s&.,\'-]+)', text)
    if ms_match:
        return ("M/s " + ms_match.group(1).strip(" :.-,")).strip()

    return ""


def parse_prchi_text(text, known_customers=None, known_amounts=None):
    """
    Parses OCR text of prchi slip and returns extracted Date, Price, and Customer Name.
    """
    clean_text = clean_ocr_text(text)
    date_str = extract_date(clean_text)
    price = extract_price(clean_text, known_amounts)
    customer_name = extract_customer_name(clean_text, known_customers)

    return {
        "raw_text": clean_text,
        "date": date_str,
        "price": price,
        "amount": price,  # Alias for compatibility
        "customer_name": customer_name,
        "has_extraction": bool(date_str or (price is not None) or customer_name)
    }
