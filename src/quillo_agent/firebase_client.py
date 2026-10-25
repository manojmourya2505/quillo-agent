"""Connects to Firestore with the service account key. Other modules get data through here."""

from functools import lru_cache

import firebase_admin
from firebase_admin import auth, credentials, firestore

from quillo_agent.config import get_settings


@lru_cache(maxsize=1)
def _app() -> firebase_admin.App:
    settings = get_settings()
    cred = credentials.Certificate(settings.firebase_service_account_path)
    return firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})


def get_db():
    """Return the Firestore client for the Quillo project."""
    return firestore.client(app=_app())


def uid_for_email(email: str) -> str:
    """Look up a Firebase user ID from an account email."""
    return auth.get_user_by_email(email, app=_app()).uid
