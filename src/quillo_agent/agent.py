"""The agent loop: ask the model, run the tools it requests, repeat until it gives an answer.

Read tools run straight away. Money actions are only prepared, and run after the user replies yes.
"""

import json
import uuid
from functools import cached_property

from openai import OpenAI

from quillo_agent.actions import (
    ACTION_SCHEMAS,
    CHECK_TOOL,
    PROPOSE_TOOLS,
    add_to_goal,
    find_goal,
    find_unpaid_bill,
    finish_bill_payment,
    inr,
    send_money,
    start_bill_payment,
)
from quillo_agent.razorpay_client import payment_link_status
from quillo_agent.config import get_settings
from quillo_agent.firebase_client import uid_for_email
from quillo_agent.prompts import SYSTEM_PROMPT
from quillo_agent.tool_descriptions import TOOL_SCHEMAS
from quillo_agent.tools import TOOLS

MAX_STEPS = 6
FALLBACK_ANSWER = "I could not finish answering that. Please try asking in a simpler way."
CONFIRM_WORDS = {"yes", "y", "yes confirm", "confirm", "ok", "okay", "yes please", "go ahead"}


def _is_confirmation(text: str) -> bool:
    return text.strip().lower().rstrip(".!") in CONFIRM_WORDS


class QuilloAgent:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = OpenAI(api_key=self.settings.openai_api_key)
        self.pending: dict[str, tuple] = {}  # action_id -> (function, kwargs), waiting for "yes"
        self._user_confirmed = False
        self.open_links: dict[str, dict] = {}  # Razorpay link id -> bill waiting to be paid

    @cached_property
    def uid(self) -> str:
        """The Quillo user whose data the agent reads, looked up from the email in .env."""
        return uid_for_email(self.settings.quillo_user_email)

    def _propose(self, name: str, args: dict) -> dict:
        if name == "propose_send_money":
            recipient = str(args["recipient"]).strip()
            amount = float(args["amount"])
            note = str(args.get("note", "")).strip()
            if amount <= 0:
                raise ValueError("Amount must be more than zero.")
            text = f"Send {inr(amount)} to {recipient}"
            text += f", note: {note}." if note else "."
            function, kwargs = send_money, {"recipient": recipient, "amount": amount, "note": note}
        elif name == "propose_pay_bill":
            bill = find_unpaid_bill(self.uid, str(args["bill_name"]))[0].to_dict()
            amount = float(bill.get("amount") or 0)
            text = f"Pay {bill['name']} of {inr(amount)} through a Razorpay payment link."
            function, kwargs = start_bill_payment, {"bill_name": bill["name"]}
        else:  # propose_add_to_goal
            goal_name = find_goal(self.uid, str(args["goal_name"]))[0].to_dict()["name"]
            amount = float(args["amount"])
            if amount <= 0:
                raise ValueError("Amount must be more than zero.")
            text = f"Add {inr(amount)} from your balance to {goal_name}."
            function, kwargs = add_to_goal, {"goal_name": goal_name, "amount": amount}

        action_id = uuid.uuid4().hex[:8]
        self.pending[action_id] = (function, kwargs)
        return {"action_id": action_id, "summary": text + " Reply yes to confirm."}

    def _confirm(self, action_id: str) -> str:
        if not self._user_confirmed:
            raise ValueError("The user has not confirmed yet. Show the summary and ask them to reply yes.")
        if action_id not in self.pending:
            raise ValueError("Unknown or already used action.")
        function, kwargs = self.pending.pop(action_id)
        result = function(self.uid, **kwargs)
        if isinstance(result, dict) and "link_id" in result:  # a payment link: remember it until it is paid
            self.open_links[result["link_id"]] = result
        return result

    def _check_payment(self, link_id: str) -> dict:
        ids = [link_id] if link_id else list(self.open_links)
        if not ids:
            raise ValueError("There are no open payment links.")
        results = []
        for lid in ids:
            info = self.open_links.get(lid)
            if info is None:
                raise ValueError("Unknown payment link.")
            status = payment_link_status(lid)
            if status == "paid":
                message = finish_bill_payment(self.uid, info["bill_name"], info["amount"])
                del self.open_links[lid]
                results.append({"link_id": lid, "status": "paid", "message": f"Payment done. {message}"})
            else:
                results.append({"link_id": lid, "status": status, "message": "Not paid yet."})
        return {"payments": results}

    def run_tool(self, name: str, args: dict) -> dict:
        """Run one tool. Errors go back to the model as data instead of crashing the loop."""
        try:
            if name in TOOLS:
                return {"result": TOOLS[name](self.uid, **args)}
            if name in PROPOSE_TOOLS:
                return {"result": self._propose(name, args)}
            if name == CHECK_TOOL:
                return {"result": self._check_payment(str(args.get("link_id", "")))}
            if name == "confirm_action":
                return {"result": self._confirm(str(args["action_id"]))}
            return {"error": f"Unknown tool: {name}"}
        except Exception as exc:
            return {"error": str(exc)}

    def _run_latest_pending(self) -> str:
        """A plain yes runs the latest prepared action directly, so the model never has to re-propose it."""
        action_id = next(reversed(self.pending))
        function, kwargs = self.pending[action_id]
        self.pending.clear()  # stale proposals can't run later
        try:
            result = function(self.uid, **kwargs)
        except Exception as exc:
            return f"That did not go through: {exc}"
        if isinstance(result, dict) and "link_id" in result:
            self.open_links[result["link_id"]] = result
            return (f"Here is the payment link for {result['bill_name']} "
                    f"({inr(result['amount'])}): {result['short_url']}\n\n"
                    "Open it to pay. When you are done, tell me you paid.")
        return result

    def ask(self, question: str, history: list[dict] | None = None) -> str:
        """Answer one question. Pass earlier messages in history to continue a conversation."""
        self._user_confirmed = _is_confirmation(question)
        if self._user_confirmed and self.pending:
            return self._run_latest_pending()
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages += history or []
        messages.append({"role": "user", "content": question})
        tools = TOOL_SCHEMAS + ACTION_SCHEMAS

        for _ in range(MAX_STEPS):
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                tools=tools,
            )
            message = response.choices[0].message
            if not message.tool_calls:
                return message.content or FALLBACK_ANSWER

            messages.append(message.model_dump(exclude_none=True))
            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                result = self.run_tool(call.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, default=str),
                })
        return FALLBACK_ANSWER
