"""Descriptions of the read-only tools, in the format the OpenAI API uses for tool calling.

The user ID is not listed here. The agent adds it, so the model never has to guess whose data it is reading.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_balance",
            "description": (
                "Get the user's account summary: current balance, money available to spend, "
                "amount saved this year, and the name and amount of the next bill. "
                "Use for questions about how much money they have or can spend."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_cards",
            "description": (
                "List the user's cards with label, last 4 digits, kind, whether it is a credit card, "
                "and whether it is frozen. Use for questions about their cards."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_goals",
            "description": (
                "List the user's savings goals with the amount saved, the target, and the percentage done. "
                "Use for questions about goals, savings progress, or how close they are to a target."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_bills",
            "description": (
                "List the user's bills that are not paid yet, with name, amount and due date. "
                "Use for questions about upcoming or unpaid bills."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_transactions",
            "description": (
                "List the user's most recent transactions, newest first, with title, amount, day and time. "
                "Use for questions about spending, payments, or recent activity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many transactions to return, from 1 to 50. Default 10.",
                        "minimum": 1,
                        "maximum": 50,
                    }
                },
                "required": [],
            },
        },
    },
]
