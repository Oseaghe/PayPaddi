import re

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)

PAYMENT_KEYWORDS = {"create", "generate", "make", "send", "payment", "link", "request", "pay", "charge"}
SUMMARY_KEYWORDS = {"summary", "sales", "revenue", "made", "earned", "received", "transactions", "much", "report", "overview"}
PDF_KEYWORDS = {"pdf", "download", "export", "report", "daily report"}
CHECK_KEYWORDS = {"check", "status", "verify", "find", "search", "chex"}

PERIOD_MAP = {
    "today": "daily", "daily": "daily",
    "this week": "weekly", "week": "weekly", "weekly": "weekly",
    "this month": "monthly", "month": "monthly", "monthly": "monthly",
    "this quarter": "quarterly", "quarter": "quarterly", "quarterly": "quarterly",
    "this year": "yearly", "year": "yearly", "yearly": "yearly", "annual": "yearly",
}


def detect_intent(text: str) -> dict:
    lower = text.lower().strip()

    # Fallback commands
    if lower == "1":
        return {"intent": "create_payment", "amount": None, "customer_name": None, "description": None}
    if lower == "2":
        return {"intent": "summary", "period": "daily"}
    if lower == "3":
        return {"intent": "pdf_report"}

    # UUID lookup — check before anything else so UUID digits don't trigger payment intent
    uuid_match = UUID_RE.search(text)
    if uuid_match:
        return {"intent": "check_payment", "reference": uuid_match.group(0)}

    words = set(re.findall(r"\w+", lower))

    # PDF report
    if words & PDF_KEYWORDS:
        return {"intent": "pdf_report"}

    # Summary intent
    if words & SUMMARY_KEYWORDS:
        result = {"intent": "summary", "period": "daily"}
        for phrase, period in PERIOD_MAP.items():
            if phrase in lower:
                result["period"] = period
                break
        return result

    # Payment intent
    amount_match = re.search(r"[₦#]?\s*(\d[\d,]*(?:\.\d+)?)([kK]?)", text)
    if amount_match and (words & PAYMENT_KEYWORDS or amount_match):
        amount = float(amount_match.group(1).replace(",", ""))
        if amount_match.group(2) == "k":
            amount *= 1000
        result = {
            "intent": "create_payment",
            "amount": amount,
            "customer_name": None,
            "description": None,
        }

        # Customer name: capitalised words after "for"
        name_match = re.search(r"\bfor\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", text)
        if name_match:
            result["customer_name"] = name_match.group(1)

        # Description: text after the amount
        after_amount = text[amount_match.end():].strip(" ,.")
        if after_amount:
            result["description"] = re.sub(r"^(naira|ngn)\b", "", after_amount, flags=re.IGNORECASE).strip()

        return result

    return {"intent": "unknown", "amount": None, "customer_name": None, "description": None, "period": "daily"}
