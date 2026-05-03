# BENIGN TEST SCRIPT
# SW Copilot backend smoke test — standalone, no pytest required.
#
# Usage (from inside agent-backend\):
#   python smoke_test.py
#
# Exits with code 0 if all checks pass, code 1 if any check fails.
# Requires the backend to be running: uvicorn main:app --host 127.0.0.1 --port 8001
#
# All payloads are obviously benign synthetic strings.
# No PowerShell, no Invoke-RestMethod.

import os
import sys
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8001"
TIMEOUT = 30.0


# ── Token loading ──────────────────────────────────────────────────────────────

def _token_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        base = Path(local_app_data)
    else:
        base = Path.home() / "AppData" / "Local"
    return base / "SwCopilotAddin" / "backend.token"


def load_token() -> str:
    path = _token_path()
    if not path.exists():
        print(f"[FATAL] Token file not found: {path}")
        print("        Start the backend first: uvicorn main:app --host 127.0.0.1 --port 8001")
        sys.exit(1)
    token = path.read_text(encoding="utf-8").strip()
    if not token:
        print(f"[FATAL] Token file is empty: {path}")
        sys.exit(1)
    print(f"[INFO]  Token loaded from {path}")
    return token


# ── Check helpers ──────────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def record(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    _results.append((name, passed, detail))


# ── Smoke checks ──────────────────────────────────────────────────────────────

def check_health(client: httpx.Client, headers: dict) -> None:
    print("\n--- GET /health ---")
    try:
        resp = client.get("/health", headers=headers)
    except httpx.ConnectError:
        record("health reachable", False, "Connection refused — is the backend running?")
        return

    record("health status 200", resp.status_code == 200, f"got {resp.status_code}")
    if resp.status_code != 200:
        record("health body", False, resp.text[:200])
        return

    data = resp.json()
    print(f"  [INFO]  status={data.get('status')}  model={data.get('model')}  "
          f"vector_docs={data.get('vector_docs')}")
    record("health status field is ok", data.get("status") == "ok",
           f"got {data.get('status')!r}")
    record("health model field present", "model" in data)
    record("health vector_docs field present", "vector_docs" in data)


def check_generate_cube(client: httpx.Client, headers: dict) -> None:
    print("\n--- POST /generate: 10mm cube ---")
    body = {
        "prompt": "make a 10mm cube",
        "context": {
            "document_type": "Part",
            "body_count": 0,
            "selected_ids": [],
            "file_path": "",
        },
    }
    try:
        resp = client.post("/generate", json=body, headers=headers)
    except httpx.ConnectError:
        record("generate/cube reachable", False, "Connection refused")
        return

    record("generate/cube status 200", resp.status_code == 200, f"got {resp.status_code}")
    if resp.status_code != 200:
        record("generate/cube body", False, resp.text[:300])
        return

    data = resp.json()
    cmd = data.get("cad_command")
    record("generate/cube cad_command present", cmd is not None)
    record("generate/cube macro_code is None", data.get("macro_code") is None,
           f"got {data.get('macro_code')!r}")

    if cmd is not None:
        action = cmd.get("action", "")
        shape = cmd.get("shape_type", "")
        dims = cmd.get("dimensions_meters", {})
        print(f"  [INFO]  action={action}  shape_type={shape}  dimensions={dims}")
        record("generate/cube action is create_shape", action == "create_shape",
               f"got {action!r}")
        record("generate/cube shape_type is box", shape == "box", f"got {shape!r}")
        # All dimensions for a cube must be the same and positive
        length = dims.get("length", 0)
        width = dims.get("width", 0)
        height = dims.get("height", 0) or dims.get("depth", 0) or 0
        record("generate/cube dimensions positive",
               all(v is not None and v > 0 for v in (length, width, height)),
               f"l={length} w={width} h={height}")


def check_generate_delete_all(client: httpx.Client, headers: dict) -> None:
    print("\n--- POST /generate: delete all features ---")
    body = {
        "prompt": "delete all features",
        "context": {
            "document_type": "Part",
            "body_count": 2,
            "selected_ids": [],
            "file_path": "",
        },
    }
    try:
        resp = client.post("/generate", json=body, headers=headers)
    except httpx.ConnectError:
        record("generate/delete reachable", False, "Connection refused")
        return

    record("generate/delete status 200", resp.status_code == 200, f"got {resp.status_code}")
    if resp.status_code != 200:
        record("generate/delete body", False, resp.text[:300])
        return

    data = resp.json()
    cmd = data.get("cad_command")
    record("generate/delete cad_command present", cmd is not None)
    record("generate/delete macro_code is None", data.get("macro_code") is None)

    if cmd is not None:
        action = cmd.get("action", "")
        print(f"  [INFO]  action={action}")
        record("generate/delete action is delete_all", action == "delete_all",
               f"got {action!r}")


def check_auth_rejection(client: httpx.Client) -> None:
    print("\n--- Auth rejection checks ---")
    try:
        resp = client.get("/health")
    except httpx.ConnectError:
        record("auth rejection reachable", False, "Connection refused")
        return

    record("health no-token returns 403", resp.status_code == 403, f"got {resp.status_code}")

    resp2 = client.post(
        "/generate",
        json={"prompt": "benign test prompt", "context": {}},
        headers={"X-Copilot-Token": "synthetic_wrong_token_for_smoke_test"},
    )
    record("generate wrong-token returns 403", resp2.status_code == 403,
           f"got {resp2.status_code}")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== SW Copilot Backend Smoke Test ===")
    token = load_token()
    headers = {"X-Copilot-Token": token}

    with httpx.Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        check_auth_rejection(client)
        check_health(client, headers)
        check_generate_cube(client, headers)
        check_generate_delete_all(client, headers)

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n=== Summary ===")
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = sum(1 for _, ok, _ in _results if not ok)
    total = len(_results)
    print(f"  {passed}/{total} checks passed, {failed} failed")

    if failed:
        print("\nFailed checks:")
        for name, ok, detail in _results:
            if not ok:
                print(f"  [FAIL] {name}" + (f": {detail}" if detail else ""))
        sys.exit(1)
    else:
        print("\nAll checks PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
