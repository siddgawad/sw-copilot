# BENIGN TEST SCRIPT
# Shared pytest fixtures for SW Copilot backend test suite.
# All test payloads in this file are synthetic and obviously benign.
# No PowerShell, no Invoke-RestMethod, no real exploit strings.

import os
import sys
from pathlib import Path

import httpx
import pytest

# ── Path setup ────────────────────────────────────────────────────────────────
# Tests are run from agent-backend\ so main.py and models\ are importable.
# If pytest is invoked from the repo root, add agent-backend to sys.path.
_BACKEND_DIR = Path(__file__).parent.parent  # agent-backend\
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_URL = "http://127.0.0.1:8001"


# ── Token loading ─────────────────────────────────────────────────────────────

def _token_file_path() -> Path:
    """Return the path to the backend token written by the server at startup."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "SwCopilotAddin" / "backend.token"


def load_token() -> str | None:
    """Read the token from disk. Returns None if the file does not exist."""
    path = _token_file_path()
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return None


# ── Backend reachability check ────────────────────────────────────────────────

def backend_is_reachable() -> bool:
    """Return True if the backend is running and responding on localhost:8001."""
    try:
        httpx.get(BASE_URL + "/health", timeout=2.0)
        # Any response (including 403) means the server is up.
        return True
    except (httpx.ConnectError, httpx.TimeoutException):
        return False


BACKEND_RUNNING = backend_is_reachable()

# Marker / skip helper for tests that require a live backend.
requires_backend = pytest.mark.skipif(
    not BACKEND_RUNNING,
    reason="Backend not running on localhost:8001 — start with: uvicorn main:app --host 127.0.0.1 --port 8001",
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def base_url() -> str:
    return BASE_URL


@pytest.fixture(scope="session")
def valid_token() -> str | None:
    """Return the current valid backend token, or None if not found on disk."""
    return load_token()


@pytest.fixture(scope="session")
def auth_headers(valid_token) -> dict[str, str]:
    """Return headers dict with the valid token. Skips the test if token is missing."""
    if valid_token is None:
        pytest.skip(
            "Token file not found at %LOCALAPPDATA%\\SwCopilotAddin\\backend.token — "
            "start the backend first so it writes the token."
        )
    return {"X-Copilot-Token": valid_token}


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    """Synchronous httpx client pointing at the local backend."""
    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:
        yield c


# ── Benign request body factories ─────────────────────────────────────────────

def make_generate_body(prompt: str) -> dict:
    """Return a valid GenerateRequest payload for the given prompt."""
    return {
        "prompt": prompt,
        "context": {
            "document_type": "Part",
            "body_count": 0,
            "selected_ids": [],
            "file_path": "",
        },
    }
