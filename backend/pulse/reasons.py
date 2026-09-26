import re
from collections import defaultdict

REASON_SQL = "COALESCE(NULLIF(TRIM(PROVIDER_RESPONSE_MESSAGE), ''), NULLIF(TRIM(CBA_MESSAGE), ''))"

NOT_RECORDED = "No reason recorded"

RULES = [
    (r"insufficient (funds|balance)", "Insufficient funds", "customer"),
    (r"account on pnd|post.?no.?debit", "Account restricted (PND)", "account"),
    (r"debit limit|transfer limit|limit exceeded", "Transfer limit exceeded", "customer"),
    (r"invalid (virtual )?account|unknown bank|invalid beneficiary", "Invalid beneficiary account", "customer"),
    (r"beneficiary institution not available|bank not available|institution not available", "Beneficiary bank not available", "system"),
    (r"timed? ?out|timeout", "Timed out at destination", "system"),
    (r"http error|connection|service unavailable", "Connection error to provider", "system"),
    (r"request in progress|in progress|pending", "Stuck in progress at provider", "system"),
    (r"invalid amount|invalid json|must not be blank|format error|validation", "Request rejected (app/validation)", "system"),
    (r"do not honou?r", "Declined by destination bank", "system"),
]

COMPILED = [(re.compile(p, re.I), label, kind) for p, label, kind in RULES]

HINTS = {
    "Insufficient funds": "Customer-side, not a system fault.",
    "Account restricted (PND)": "These accounts are on Post-No-Debit, usually KYC or compliance holds ops can review.",
    "Transfer limit exceeded": "Customers are hitting daily or per-transaction limits. Worth reviewing limit tiers.",
    "Invalid beneficiary account": "Customers are entering wrong account numbers.",
    "Beneficiary bank not available": "Points to a destination bank or NIP outage.",
    "Timed out at destination": "Points to switch or destination latency.",
    "Connection error to provider": "The link to the payment provider is failing.",
    "Stuck in progress at provider": "The provider has not confirmed these yet.",
    "Request rejected (app/validation)": "The app is sending requests the provider rejects. Likely an app bug.",
    "Declined by destination bank": "Destination banks are declining.",
    NOT_RECORDED: "Failures saved without any message. A logging gap worth raising.",
}

DEFAULT_HINT = "Worth investigating."


def classify(message):
    text = (message or "").strip()
    if not text:
        return NOT_RECORDED, "unknown"
    for pattern, label, kind in COMPILED:
        if pattern.search(text):
            return label, kind
    cleaned = re.sub(r"[:(]?\s*\d{6,}\s*\)?", "", text).strip(" :-")
    return (cleaned[:60] or NOT_RECORDED), "other"


def group(rows, fields):
    out = defaultdict(lambda: dict.fromkeys(fields, 0))
    kinds = {}
    for r in rows:
        label, kind = classify(r["reason"])
        kinds[label] = kind
        for f in fields:
            out[label][f] += int(r[f] or 0)
    return [{"reason": label, "kind": kinds[label], **counts} for label, counts in out.items()]
