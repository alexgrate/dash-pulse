import re
from collections import defaultdict

REASON_SQL = "COALESCE(NULLIF(TRIM(PROVIDER_RESPONSE_MESSAGE), ''), NULLIF(TRIM(CBA_MESSAGE), ''))"

NOT_RECORDED = "No reason recorded"

RULES = [
    (r"insufficient (funds|balance)", "Insufficient funds", "customer"),
    (r"account on pnd|post.?no.?debit", "Customer's account is frozen", "account"),
    (r"debit limit|transfer limit|limit exceeded", "Transfer limit exceeded", "customer"),
    (r"invalid (virtual )?account|unknown bank|invalid beneficiary", "Wrong account number entered", "customer"),
    (r"beneficiary institution not available|bank not available|institution not available", "Receiving bank is down", "system"),
    (r"timed? ?out|timeout", "Receiving bank took too long to reply", "system"),
    (r"http error|connection|service unavailable", "Could not reach our payment partner", "system"),
    (r"request in progress|in progress|pending", "Waiting for payment partner to confirm", "system"),
    (r"invalid amount|invalid json|must not be blank|format error|validation", "Our app sent a faulty request", "system"),
    (r"do not honou?r", "Receiving bank refused it", "system"),
]

COMPILED = [(re.compile(p, re.I), label, kind) for p, label, kind in RULES]

HINTS = {
    "Insufficient funds": "Customers did not have enough money. Not a fault at Dash.",
    "Customer's account is frozen": "These accounts are blocked from sending money (Post-No-Debit), usually a KYC or compliance hold that ops can review.",
    "Transfer limit exceeded": "Customers are hitting their daily or per-transfer limit. Worth reviewing the limits.",
    "Wrong account number entered": "Customers typed an account number that does not exist.",
    "Receiving bank is down": "The other bank, or the NIP network between banks, is having an outage.",
    "Receiving bank took too long to reply": "The other bank or the network between banks is slow right now.",
    "Could not reach our payment partner": "Dash could not get through to the company that carries our transfers to other banks. Usually their outage or our network link, and the tech team should check it now.",
    "Waiting for payment partner to confirm": "Our payment partner has not yet said whether these went through.",
    "Our app sent a faulty request": "The Dash app sent something our payment partner rejected. Likely a bug for the tech team.",
    "Receiving bank refused it": "The other bank declined these transfers.",
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
