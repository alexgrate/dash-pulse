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
    "Insufficient funds": "customer-side, not a system fault",
    "Account restricted (PND)": "accounts on Post-No-Debit, usually KYC or compliance holds that ops can review",
    "Transfer limit exceeded": "customers hitting daily or per-transaction limits; worth reviewing limit tiers",
    "Invalid beneficiary account": "customers entering wrong account numbers",
    "Beneficiary bank not available": "points to a destination bank or NIP outage",
    "Timed out at destination": "points to switch or destination latency",
    "Connection error to provider": "the link to the payment provider is failing",
    "Stuck in progress at provider": "the provider has not confirmed these yet",
    "Request rejected (app/validation)": "the app sent requests the provider rejected; likely an app bug",
    "Declined by destination bank": "destination banks are declining",
    NOT_RECORDED: "failures saved without any message; a logging gap worth raising",
}


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
