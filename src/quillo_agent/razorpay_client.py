"""Razorpay test-mode payment links. Creates a link the user opens to pay, and checks whether it was paid."""

import httpx

from quillo_agent.config import get_settings

BASE = "https://api.razorpay.com/v1"


def _auth() -> tuple[str, str]:
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay keys are not set in .env.")
    if not settings.razorpay_key_id.startswith("rzp_test_"):
        raise RuntimeError("Only Razorpay test keys are allowed here.")
    return settings.razorpay_key_id, settings.razorpay_key_secret


def create_payment_link(amount_rupees: float, description: str) -> dict:
    """Create a payment link for amount_rupees. Returns its id and the URL the user opens."""
    paise = round(amount_rupees * 100)
    if paise <= 0:
        raise ValueError("Amount must be more than zero.")
    response = httpx.post(
        f"{BASE}/payment_links",
        auth=_auth(),
        json={"amount": paise, "currency": "INR", "description": description[:200]},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    return {"id": data["id"], "short_url": data["short_url"], "status": data["status"]}


def payment_link_status(link_id: str) -> str:
    """Return 'paid', 'created', 'partially_paid', 'expired' or 'cancelled'."""
    response = httpx.get(f"{BASE}/payment_links/{link_id}", auth=_auth(), timeout=20)
    response.raise_for_status()
    return response.json()["status"]
