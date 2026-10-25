"""Tests for the read-only tools. Most use sample data, so they never touch the database.
The one test marked 'live' reads the real account (read-only) to confirm the connection works."""

import pytest

from quillo_agent import tools
from quillo_agent.agent import QuilloAgent
from quillo_agent.tool_descriptions import TOOL_SCHEMAS

SAMPLE = {
    "cards": [
        {"label": "Debit", "last4": "4821", "kind": "debit", "isCredit": False, "frozen": True, "order": 1},
        {"label": "Credit", "last4": "0937", "kind": "credit", "isCredit": True, "order": 2},
    ],
    "goals": [
        {"name": "Trip", "saved": 50000, "target": 200000, "order": 2},
        {"name": "Fund", "saved": 0, "target": 0, "order": 1},
    ],
    "bills": [
        {"name": "Power", "amount": 2184, "due": "28 Oct", "order": 1},
        {"name": "Phone", "amount": 499, "due": "30 Oct", "paid": True, "order": 2},
    ],
    "transactions": [{"title": f"t{i}", "amount": -i, "order": i} for i in range(1, 15)],
}


@pytest.fixture
def sample(monkeypatch):
    monkeypatch.setattr(tools, "_docs", lambda uid, collection: SAMPLE.get(collection, []))


def test_cards_sorted_and_only_last4(sample):
    cards = tools.list_cards("u")
    assert [c["label"] for c in cards] == ["Debit", "Credit"]
    assert cards[0]["frozen"] is True
    assert cards[1]["is_credit"] is True
    assert all(len(c["last4"]) == 4 for c in cards)
    assert all(set(c) == {"label", "last4", "kind", "is_credit", "frozen"} for c in cards)


def test_goal_percent_done(sample):
    goals = tools.list_goals("u")
    assert [g["name"] for g in goals] == ["Fund", "Trip"]
    assert goals[0]["percent_done"] == 0  # target 0 must not divide by zero
    assert goals[1]["percent_done"] == 25


def test_only_unpaid_bills(sample):
    assert [b["name"] for b in tools.list_bills("u")] == ["Power"]


def test_transactions_limit_is_clamped(sample):
    assert [t["title"] for t in tools.list_transactions("u", limit=3)] == ["t1", "t2", "t3"]
    assert len(tools.list_transactions("u", limit=500)) == 14  # capped at 50, only 14 exist
    assert len(tools.list_transactions("u", limit=0)) == 1  # floor of 1


def test_schemas_match_tools():
    names = {t["function"]["name"] for t in TOOL_SCHEMAS}
    assert names == set(tools.TOOLS)


def test_unknown_tool_returns_error_not_crash():
    agent = QuilloAgent()
    assert "error" in agent.run_tool("delete_everything", {})


@pytest.mark.live
def test_live_balance_has_expected_fields():
    from quillo_agent.config import get_settings
    from quillo_agent.firebase_client import uid_for_email

    uid = uid_for_email(get_settings().quillo_user_email)
    data = tools.get_balance(uid)
    assert set(data) == {"balance", "availableDebit", "savedThisYear", "nextBillName", "nextBillAmount"}


# ---- Money actions: confirmation gate and formatting (no real writes happen here) ----

from quillo_agent.actions import ACTION_SCHEMAS, inr  # noqa: E402
from quillo_agent.agent import _is_confirmation  # noqa: E402


def test_indian_rupee_formatting():
    assert inr(124000) == "₹1,24,000.00"
    assert inr(2184) == "₹2,184.00"
    assert inr(500) == "₹500.00"
    assert inr(1234567.5) == "₹12,34,567.50"


def test_action_schema_names():
    names = {t["function"]["name"] for t in ACTION_SCHEMAS}
    assert names == {"propose_send_money", "propose_pay_bill", "propose_add_to_goal", "confirm_action", "check_payment"}


def test_confirmation_words():
    assert _is_confirmation("yes")
    assert _is_confirmation("Yes.")
    assert _is_confirmation(" ok ")
    assert not _is_confirmation("no")
    assert not _is_confirmation("yes but make it 500")


def test_confirm_is_blocked_without_user_yes():
    agent = QuilloAgent()
    agent.uid = "u"
    agent._user_confirmed = False
    agent.pending["abc"] = (lambda uid: "done", {})
    assert "error" in agent.run_tool("confirm_action", {"action_id": "abc"})
    assert "abc" in agent.pending  # still waiting for a real yes


def test_confirm_runs_after_user_yes():
    agent = QuilloAgent()
    agent.uid = "u"
    agent._user_confirmed = True
    agent.pending["abc"] = (lambda uid, amount: f"done {amount}", {"amount": 5})
    assert agent.run_tool("confirm_action", {"action_id": "abc"}) == {"result": "done 5"}
    assert "abc" not in agent.pending  # an action can only run once


def test_plain_yes_runs_latest_pending_without_model():
    agent = QuilloAgent()
    agent.uid = "u"
    agent.pending["old"] = (lambda uid: "stale", {})
    agent.pending["new"] = (lambda uid, amount: f"Sent {amount}", {"amount": 500})
    # the model is never called: a plain yes goes straight to the pending action
    agent.client = None
    assert agent.ask("yes") == "Sent 500"
    assert agent.pending == {}
