import re

ALIASES = {
    "OPAY": "OPay",
    "OPAY DIGITAL SERVICES": "OPay",
    "PALMPAY": "PalmPay",
    "MONIEPOINT MFB": "Moniepoint MFB",
    "GTBANK": "GTBank",
    "GUARANTY TRUST BANK": "GTBank",
    "FIRST BANK OF NIGERIA": "First Bank",
    "FIRSTBANK": "First Bank",
    "UNITED BANK FOR AFRICA": "UBA",
    "STANBIC IBTC BANK": "Stanbic IBTC",
    "ECOBANK NIGERIA": "Ecobank",
    "UNION BANK OF NIGERIA": "Union Bank",
    "FIRST CITY MONUMENT BANK": "FCMB",
    "KUDA MFB": "Kuda MFB",
}

SUFFIXES = re.compile(r"\s+(PLC|LIMITED|LTD|NIGERIA LIMITED)\.?$", re.I)
REPLACEMENTS = [
    (re.compile(r"micro\s*finance\s+bank", re.I), "MFB"),
    (re.compile(r"payment\s+service\s+bank", re.I), "PSB"),
]


def canonical(name):
    text = re.sub(r"\s+", " ", (name or "").strip())
    if not text:
        return "Unknown bank"
    text = SUFFIXES.sub("", text)
    for pattern, short in REPLACEMENTS:
        text = pattern.sub(short, text)
    alias = ALIASES.get(text.upper())
    if alias:
        return alias
    if text.isupper():
        text = " ".join(w if len(w) <= 3 else w.capitalize() for w in text.split())
    return text


def key(name):
    return canonical(name).upper()
