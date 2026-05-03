# SW Copilot Backend - Developer Testing Guide

All backend tests use Python (`pytest` + `httpx`). Do not use PowerShell HTTP commands for adversarial strings; EDR tools inspect command lines and may flag them.

## Prerequisites

1. The backend virtual environment must exist at `agent-backend\.venv`.
2. The backend must be running for live network tests. Pure unit tests do not need the backend.

Start the backend:

```powershell
cd C:\projects\sw-copilot\agent-backend
.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8001
```

The backend writes a fresh token at startup:

```text
%LOCALAPPDATA%\SwCopilotAddin\backend.token
```

The test suite reads that file automatically for `X-Copilot-Token`.

## Running The Smoke Test

From inside `agent-backend\` with the backend running:

```powershell
.venv\Scripts\python.exe smoke_test.py
```

The smoke test verifies:

- Auth rejection: missing/wrong token returns `403`.
- `GET /health` with the valid token returns `status == "ok"`.
- `POST /generate` for `make a 10mm cube` returns `operation_graph`, schema `0.2`, no `macro_code`, and includes `sketch` + `extrude_boss`.
- `POST /generate` for `delete all features` returns an operation graph containing `delete_feature`.

## Running Pytest

From inside `agent-backend\`:

```powershell
cd C:\projects\sw-copilot\agent-backend
.venv\Scripts\python.exe -m pytest tests\ -v
```

From repo root:

```powershell
cd C:\projects\sw-copilot
agent-backend\.venv\Scripts\python.exe -m pytest agent-backend\tests\ -v
```

Useful focused runs:

```powershell
.venv\Scripts\python.exe -m pytest tests\test_security.py -q -k "Sanitize"
.venv\Scripts\python.exe -m pytest tests\test_security.py -q -k "TokenAuth"
.venv\Scripts\python.exe -m pytest tests\test_security.py -q
```

## Coverage

| File | Coverage | Needs backend? |
|---|---|---|
| `tests/test_security.py` - `TestTokenAuthRejection` | Missing/wrong token returns `403` | Yes |
| `tests/test_security.py` - `TestTokenAuthSuccess` | Valid token returns health/generate responses | Yes |
| `tests/test_security.py` - `TestSanitizeContextValue` | Context sanitizer removes newlines, backticks, control chars, injection markers, and caps length | No |
| `tests/test_security.py` - `TestCadCommandValidation` | Legacy schema regression coverage | No |

Tests that require the backend are decorated with `@requires_backend`. They are skipped automatically if `http://127.0.0.1:8001` is not reachable.

## Why Not PowerShell HTTP Tests?

Passing synthetic prompt-injection strings through `Invoke-RestMethod` places those strings on the PowerShell command line. Windows Defender and enterprise EDR products scan process arguments and can flag them even when they are only test data.

Keep adversarial strings inside Python source/test files and send HTTP with `httpx`.

## Troubleshooting

`Token file not found`: start the backend first.

`403 with valid token`: the token file and running backend are out of sync. Restart the backend so it writes a fresh token.

`Connection refused`: backend is not running on `127.0.0.1:8001`.

`ModuleNotFoundError: No module named 'main'`: run from `agent-backend\` or use the repo-root command above.

`503 Agents not yet initialised`: wait a few seconds after backend startup and retry.
