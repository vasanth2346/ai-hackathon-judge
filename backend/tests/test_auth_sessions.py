import time

import pytest
from fastapi import HTTPException

from app import main


@pytest.fixture(autouse=True)
def signing_key(monkeypatch):
    monkeypatch.setattr(main.settings, "auth_secret_key", "test-only-signing-key")


def token(role: str, *, expired: bool = False) -> str:
    expires = int(time.time()) - 1 if expired else int(time.time()) + 60
    return main.encode_session({"role": role, "email": "test@example.com", "exp": expires})


def test_host_accepts_current_and_legacy_host_cookie():
    session_token = token("host")

    assert main.require_host(session_token, None)["role"] == "host"
    assert main.require_host(None, session_token)["role"] == "host"


def test_participant_accepts_legacy_cookie_but_host_rejects_it():
    session_token = token("participant")

    assert main.require_participant(None, session_token)["role"] == "participant"
    with pytest.raises(HTTPException) as error:
        main.require_host(None, session_token)
    assert error.value.status_code == 401


def test_expired_legacy_host_cookie_is_rejected():
    with pytest.raises(HTTPException) as error:
        main.require_host(None, token("host", expired=True))
    assert error.value.status_code == 401
