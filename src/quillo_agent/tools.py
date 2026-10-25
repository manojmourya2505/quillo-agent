"""Read-only tools the agent can call to look up a user's Quillo data in Firestore."""

from quillo_agent.firebase_client import get_db


def _user(uid: str):
    return get_db().collection("users").document(uid)


def _docs(uid: str, collection: str) -> list[dict]:
    return [doc.to_dict() or {} for doc in _user(uid).collection(collection).stream()]


def get_balance(uid: str) -> dict:
    """Balance, money available to spend, saved this year and the next bill."""
    data = (_user(uid).collection("summary").document("main").get().to_dict()) or {}
    keys = ("balance", "availableDebit", "savedThisYear", "nextBillName", "nextBillAmount")
    return {key: data.get(key) for key in keys}


def list_cards(uid: str) -> list[dict]:
    """Cards on the account. Only the last 4 digits are returned."""
    cards = sorted(_docs(uid, "cards"), key=lambda c: c.get("order", 0))
    return [
        {
            "label": c.get("label"),
            "last4": c.get("last4"),
            "kind": c.get("kind"),
            "is_credit": bool(c.get("isCredit")),
            "frozen": bool(c.get("frozen")),
        }
        for c in cards
    ]


def list_goals(uid: str) -> list[dict]:
    """Savings goals with how much is saved and the percentage done."""
    goals = sorted(_docs(uid, "goals"), key=lambda g: g.get("order", 0))
    result = []
    for g in goals:
        saved = float(g.get("saved") or 0)
        target = float(g.get("target") or 0)
        result.append({
            "name": g.get("name"),
            "saved": saved,
            "target": target,
            "percent_done": round(saved / target * 100) if target else 0,
        })
    return result


def list_bills(uid: str) -> list[dict]:
    """Bills that are not paid yet."""
    bills = sorted(_docs(uid, "bills"), key=lambda b: b.get("order", 0))
    return [
        {"name": b.get("name"), "amount": float(b.get("amount") or 0), "due": b.get("due")}
        for b in bills
        if not b.get("paid")
    ]


def list_transactions(uid: str, limit: int = 10) -> list[dict]:
    """Most recent transactions, newest first."""
    txns = sorted(_docs(uid, "transactions"), key=lambda t: t.get("order", 0))[: max(1, min(limit, 50))]
    return [
        {
            "title": t.get("title"),
            "subtitle": t.get("subtitle"),
            "amount": float(t.get("amount") or 0),
            "day": t.get("day"),
            "time": t.get("time"),
        }
        for t in txns
    ]


TOOLS = {
    "get_balance": get_balance,
    "list_cards": list_cards,
    "list_goals": list_goals,
    "list_bills": list_bills,
    "list_transactions": list_transactions,
}
