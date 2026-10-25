"""Actions that change data: send money, pay a bill, add money to a goal.

The agent never runs these directly. It first prepares them (see agent.py), shows a summary,
and runs them only after the user confirms. The writes follow the same rules as the Quillo app.
"""

import time
from datetime import datetime

from quillo_agent.tools import _user

PROPOSE_TOOLS = {"propose_send_money", "propose_pay_bill", "propose_add_to_goal"}
CHECK_TOOL = "check_payment"

ACTION_SCHEMAS = [
    {"type": "function", "function": {
        "name": "propose_send_money",
        "description": (
            "Prepare sending money to a person. It is NOT sent yet. Before calling this, ask the user "
            "for the recipient and amount, and ask for an optional note. Returns a summary and an action_id."
        ),
        "parameters": {"type": "object", "properties": {
            "recipient": {"type": "string", "description": "Name, UPI ID or phone number"},
            "amount": {"type": "number", "description": "Amount in rupees, more than 0"},
            "note": {"type": "string", "description": "Optional note"},
        }, "required": ["recipient", "amount"]},
    }},
    {"type": "function", "function": {
        "name": "propose_pay_bill",
        "description": (
            "Prepare paying an unpaid bill from the balance. It is NOT paid yet. Use the exact bill name "
            "from list_bills. Returns a summary and an action_id."
        ),
        "parameters": {"type": "object", "properties": {
            "bill_name": {"type": "string", "description": "Bill name as listed by list_bills"},
        }, "required": ["bill_name"]},
    }},
    {"type": "function", "function": {
        "name": "propose_add_to_goal",
        "description": (
            "Prepare moving money from the balance into a savings goal. It is NOT moved yet. Use the exact "
            "goal name from list_goals. Returns a summary and an action_id."
        ),
        "parameters": {"type": "object", "properties": {
            "goal_name": {"type": "string", "description": "Goal name as listed by list_goals"},
            "amount": {"type": "number", "description": "Amount in rupees, more than 0"},
        }, "required": ["goal_name", "amount"]},
    }},
    {"type": "function", "function": {
        "name": "check_payment",
        "description": (
            "Check whether a bill payment link has been paid. Call this when the user says they paid, or asks "
            "about a payment. Leave link_id empty to check all open links. If paid, the bill is marked paid."
        ),
        "parameters": {"type": "object", "properties": {
            "link_id": {"type": "string", "description": "Optional payment link id from an earlier reply"},
        }},
    }},
    {"type": "function", "function": {
        "name": "confirm_action",
        "description": (
            "Carry out a prepared action. Only call this after the user has replied yes to the summary "
            "in their latest message."
        ),
        "parameters": {"type": "object", "properties": {
            "action_id": {"type": "string"},
        }, "required": ["action_id"]},
    }},
]


def inr(value: float) -> str:
    """Format rupees with Indian digit grouping, for example ₹1,24,000.00."""
    whole, decimals = f"{value:.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    return f"₹{whole}.{decimals}"


def _summary_ref(uid: str):
    return _user(uid).collection("summary").document("main")


def _summary(uid: str) -> dict:
    return _summary_ref(uid).get().to_dict() or {}


def _check_amount(amount: float) -> None:
    if amount <= 0:
        raise ValueError("Amount must be more than zero.")


def _check_funds(uid: str, amount: float) -> None:
    available = float(_summary(uid).get("availableDebit") or 0)
    if amount > available:
        raise ValueError(f"Amount {inr(amount)} is more than the available balance {inr(available)}.")


def _transaction_fields(amount: float, title: str, subtitle: str) -> dict:
    now = datetime.now()
    return {
        "title": title,
        "subtitle": subtitle,
        "amount": amount,
        "category": "Other",
        "time": now.strftime("%H:%M"),
        "day": "Today",
        "order": -int(time.time()),
    }


def _matching(uid: str, collection: str, name: str) -> list:
    wanted = name.strip().lower()
    return [d for d in _user(uid).collection(collection).stream()
            if str((d.to_dict() or {}).get("name", "")).lower() == wanted]


def find_unpaid_bill(uid: str, name: str) -> list:
    docs = [d for d in _matching(uid, "bills", name) if not (d.to_dict() or {}).get("paid")]
    if not docs:
        raise ValueError(f"No unpaid bill called {name}.")
    return docs


def find_goal(uid: str, name: str) -> list:
    docs = _matching(uid, "goals", name)
    if not docs:
        raise ValueError(f"No goal called {name}.")
    return docs


def send_money(uid: str, recipient: str, amount: float, note: str = "") -> str:
    _check_amount(amount)
    _check_funds(uid, amount)
    summary = _summary(uid)
    _user(uid).collection("transactions").document().set(
        _transaction_fields(-amount, recipient, note.strip() or "Sent"))
    _summary_ref(uid).update({
        "balance": float(summary.get("balance") or 0) - amount,
        "availableDebit": float(summary.get("availableDebit") or 0) - amount,
    })
    return f"Sent {inr(amount)} to {recipient}."


def start_bill_payment(uid: str, bill_name: str) -> dict:
    """Create a Razorpay test payment link for an unpaid bill. The bill is NOT marked paid here."""
    from quillo_agent.razorpay_client import create_payment_link

    bill = find_unpaid_bill(uid, bill_name)[0].to_dict()
    amount = float(bill.get("amount") or 0)
    _check_amount(amount)
    link = create_payment_link(amount, f"Bill: {bill['name']}")
    return {"link_id": link["id"], "short_url": link["short_url"],
            "bill_name": bill["name"], "amount": amount}


def finish_bill_payment(uid: str, bill_name: str, amount: float) -> str:
    """Run after Razorpay says the link is paid: mark the bill paid and update balance and next bill."""
    docs = find_unpaid_bill(uid, bill_name)
    bill = docs[0].to_dict()
    summary = _summary(uid)
    for doc in docs:
        doc.reference.update({"paid": True})
    _user(uid).collection("transactions").document().set(
        _transaction_fields(-amount, bill["name"], "Bill payment"))
    remaining = sorted(
        [d.to_dict() for d in _user(uid).collection("bills").stream() if not (d.to_dict() or {}).get("paid")],
        key=lambda b: b.get("order", 0),
    )
    following = remaining[0] if remaining else {}
    _summary_ref(uid).update({
        "balance": float(summary.get("balance") or 0) - amount,
        "nextBillName": following.get("name", ""),
        "nextBillAmount": float(following.get("amount") or 0),
    })
    return f"Paid {bill['name']} ({inr(amount)})."


def add_to_goal(uid: str, goal_name: str, amount: float) -> str:
    _check_amount(amount)
    _check_funds(uid, amount)
    goal_doc = find_goal(uid, goal_name)[0]
    goal = goal_doc.to_dict()
    summary = _summary(uid)
    goal_doc.reference.update({"saved": float(goal.get("saved") or 0) + amount})
    _user(uid).collection("transactions").document().set(
        _transaction_fields(-amount, f"Saved for {goal['name']}", "Goal transfer"))
    _summary_ref(uid).update({
        "balance": float(summary.get("balance") or 0) - amount,
        "availableDebit": float(summary.get("availableDebit") or 0) - amount,
        "savedThisYear": float(summary.get("savedThisYear") or 0) + amount,
    })
    return f"Added {inr(amount)} to {goal['name']}."
