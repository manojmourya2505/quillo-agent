# Quillo Agent

The Quillo Agent is the assistant behind the **Ask Quillo** screen in the Quillo Android app. It answers questions about your money from your own Firestore data, and it can prepare three actions for you to confirm: send money to a person, pay a bill through a Razorpay test link, and add money to a savings goal.

Nothing is sent, paid or moved until you reply **yes**. Bills are marked paid only after Razorpay confirms the payment.

The agent is written in Python. It uses OpenAI (`gpt-4o-mini` by default) for language and tool calling, Firebase Admin for your data, and FastAPI for the HTTP server the app calls.

## How a request flows

```
Quillo app (Ask screen)
   │  POST /ask  with "Authorization: Bearer <token>"
   ▼
api.py  ── checks the token against users/{uid}/agent/config in Firestore
   │
   ▼
agent.py  (the loop: ask the model → run its tools → repeat, max 6 steps)
   ├── read tools (tools.py)        balance, cards, goals, bills, transactions
   ├── propose tools (actions.py)   prepare send / pay bill / add to goal, return a summary
   ├── a plain "yes" (agent.py)     runs the latest prepared action directly
   └── check_payment (agent.py)     asks Razorpay if a bill link is paid
   │
   ▼
Firestore (users/{uid}/...)        Razorpay test API (payment links)
```

## Files, one by one

| File | What it does |
|---|---|
| `src/quillo_agent/config.py` | Loads `.env` and checks every required setting once. Fails with a clear message if one is missing. |
| `src/quillo_agent/firebase_client.py` | Starts Firebase Admin with the service account file. Looks up your user ID from your email. |
| `src/quillo_agent/tools.py` | Read-only tools: `get_balance`, `list_cards`, `list_goals`, `list_bills`, `list_transactions`. Each one reads your Firestore data. |
| `src/quillo_agent/tool_descriptions.py` | The JSON descriptions of the read tools that the model sees. |
| `src/quillo_agent/actions.py` | The money actions. It validates amounts and funds, formats rupees (`₹1,24,000.00`), and writes to Firestore the same way the app does. Also creates the bill payment link. |
| `src/quillo_agent/razorpay_client.py` | Creates Razorpay **test** payment links and checks whether they are paid. Refuses any key that does not start with `rzp_test_`. |
| `src/quillo_agent/prompts.py` | The instructions the model follows: answer from the data, ask for missing details one at a time, show a summary, act only after a yes. |
| `src/quillo_agent/agent.py` | The agent loop. Holds the pending actions and open payment links in memory. Runs a plain "yes" directly. |
| `src/quillo_agent/api.py` | The HTTP server: `GET /health` and `POST /ask`. Checks the token on every `/ask` call. |
| `src/quillo_agent/main.py` | A terminal chat for testing on your computer. |
| `tests/test_tools.py` | Tests for formatting, the confirmation rules, and the payment-check flow. No test makes a real write. |

## What the agent can and cannot do

| Request | What happens |
|---|---|
| "What is my balance?" | Reads your summary and answers. |
| "Show my bills" / "what did I spend today?" | Reads the lists and answers. |
| "Send ₹500 to Rohith, note: rent" | Asks for anything missing, shows a summary, waits for **yes**, then moves the money inside Quillo. |
| "Pay Property tax" | Shows a summary, waits for **yes**, creates a Razorpay test link, and returns it. You pay the link. Then say you paid, and the agent checks the link. When Razorpay says paid, the bill is marked paid and the balance is reduced. |
| "Add ₹200 to Bike goal" | Shows a summary, waits for **yes**, then moves the money into the goal. |
| Top up, card changes | Not available in the assistant. Use the app's screens. |

## Confirmation rules

1. The model can only **prepare** an action. A prepared action is stored with an ID and a summary.
2. A plain reply of `yes`, `ok`, `confirm`, and similar words runs the latest prepared action directly on the server. The model is not involved, so it cannot re-propose it.
3. Any other message clears nothing and runs nothing.
4. After a prepared action runs, all prepared actions are cleared, so an old proposal cannot run later.
5. Payment links are remembered only while the server runs. If the server restarts before you pay, the bill stays unpaid and you need to pay it again.

## Setup

### Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- An OpenAI API key
- A Firebase project with Firestore and a service account key
- Razorpay **test** keys (optional, needed only for bill payments)

### Steps

1. Clone the repository and install the dependencies:

   ```bash
   uv sync
   ```

2. Copy the example settings file and fill it in:

   ```bash
   cp .env.example .env
   ```

   | Variable | Meaning |
   |---|---|
   | `OPENAI_API_KEY` | Your OpenAI key. Never commit it. |
   | `OPENAI_MODEL` | Model name, for example `gpt-4o-mini`. |
   | `FIREBASE_PROJECT_ID` | Your Firebase project ID, for example `quillo-xxxxx`. |
   | `FIREBASE_SERVICE_ACCOUNT_PATH` | Full path to the service account JSON file. |
   | `QUILLO_USER_EMAIL` | The email of the Quillo user whose data the agent reads. |
   | `APP_ENV` | `development` or `production`. |
   | `RAZORPAY_KEY_ID` | Razorpay **test** key ID (`rzp_test_...`). |
   | `RAZORPAY_KEY_SECRET` | Razorpay **test** key secret. Never commit it. |

3. Put the Firebase service account JSON somewhere outside the repository, and point `FIREBASE_SERVICE_ACCOUNT_PATH` at it. The file name is ignored by git (`serviceAccount*.json`).

4. Create the server token. The app and the server share it, and it lives in Firestore at `users/{your uid}/agent/config`, field `token`. Create it once with a long random value, for example with Python's `secrets.token_urlsafe(32)`, and store it with the Firebase Admin SDK. Do not put it in `.env` or in the repository. To change it, write a new value to the same field. The app reads it after you sign in.

### Run it

Terminal chat (for testing):

```bash
uv run quillo-agent
```

HTTP server for the Android app (run it on the same network as the phone):

```bash
uv run uvicorn quillo_agent.api:app --host 0.0.0.0 --port 8787
```

Check that it is up:

```bash
curl http://localhost:8787/health
```

Ask a question (replace `YOUR_TOKEN`):

```bash
curl -X POST http://localhost:8787/ask \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "What is my current balance?"}'
```

Requests without the right token get `401`.

### API

| Method and path | Purpose |
|---|---|
| `GET /health` | Returns `{"ok": true}`. No token needed. |
| `POST /ask` | Body: `{"question": "...", "history": [{"role": "user" or "assistant", "content": "..."}]}`. Returns `{"answer": "..."}`. Needs the token. The question is limited to 2000 characters and the history to 10 messages. |

### Tests

```bash
uv run pytest
```

The tests use sample data and do not write to Firestore. The live test (marked `live`) reads your real account and is read-only.

## Safety

- Only read tools run without confirmation. Every new money action waits for a plain "yes". `check_payment` marks a bill paid only when Razorpay reports that the link is paid.
- Only Razorpay **test** keys are accepted.
- Secrets live in `.env` and the service account file, both git-ignored. Do not commit them.
- The server is meant for your home network only. It uses plain HTTP, so do not expose it to the internet as it is.

## Limits and next steps

- The Razorpay result is checked only when you ask. Razorpay does not push it to the chat, so there is no live "payment done" message. That needs a webhook server.
- Pending actions and open payment links are held in memory. A server restart clears them.
- The agent runs on your computer. The phone can reach it only while the computer is on and on the same Wi-Fi.
