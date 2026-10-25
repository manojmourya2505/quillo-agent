"""HTTP API the Quillo app calls. Every request must carry the agent's secret token."""

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from quillo_agent.agent import QuilloAgent
from quillo_agent.firebase_client import get_db

app = FastAPI(title="Quillo agent")
_agent: QuilloAgent | None = None


def get_agent() -> QuilloAgent:
    global _agent
    if _agent is None:
        _agent = QuilloAgent()
    return _agent


def check_token(authorization: str = Header(default="")) -> None:
    """The expected token is stored in Firestore at users/{uid}/agent/config, field 'token'."""
    snapshot = get_db().collection("users").document(get_agent().uid).collection("agent").document("config").get()
    expected = str((snapshot.to_dict() or {}).get("token", "")).strip()
    if not expected:
        raise HTTPException(status_code=500, detail="Agent token is not set in Firestore")
    given = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given, expected):
        raise HTTPException(status_code=401, detail="Wrong or missing token")


class Turn(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    history: list[Turn] = Field(default_factory=list, max_length=10)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/ask", dependencies=[Depends(check_token)])
def ask(body: AskBody) -> dict:
    history = [t.model_dump() for t in body.history]
    answer = get_agent().ask(body.question, history)
    return {"answer": answer}
