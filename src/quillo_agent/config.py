"""Loads the agent's settings from the .env file in the project root."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    firebase_project_id: str
    firebase_service_account_path: str
    quillo_user_email: str
    app_env: str
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name}. Add it to the .env file in the project root.")
    return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Read and check all settings once. Raises a clear error if one is missing."""
    return Settings(
        openai_api_key=_required("OPENAI_API_KEY"),
        openai_model=_required("OPENAI_MODEL"),
        firebase_project_id=_required("FIREBASE_PROJECT_ID"),
        firebase_service_account_path=_required("FIREBASE_SERVICE_ACCOUNT_PATH"),
        quillo_user_email=_required("QUILLO_USER_EMAIL"),
        app_env=os.getenv("APP_ENV", "development").strip(),
        razorpay_key_id=os.getenv("RAZORPAY_KEY_ID", "").strip(),
        razorpay_key_secret=os.getenv("RAZORPAY_KEY_SECRET", "").strip(),
    )
