# SW Copilot Backend — Developer Testing Guide

All backend tests use Python (`pytest` + `httpx`). No PowerShell scripts, no `Invoke-RestMethod`.

---

## Prerequisites

1. The backend virtual environment must be active (or `httpx` and `pytest` must be installed).
2. The backend must be running for any live network tests (smoke test and auth-success tests).
   Unit tests (sanitization, schema validation) run without the backend.

Start the backend:

```
cd C:\Users\theof\agent-backend
uvicorn main:app --host 127.0.0.1 --port 8001
```

The backend writes a fresh token to disk at startup:

```
%LOCALAPPDATA%\SwCopilotAddin\backend.token
```

That file is the single source of truth for `X-Copilot-Token`. The test suite reads it automatically.

---

## Token file

| Property | Value |
|---|---|
| Path | `%LOCALAPPDATA%\SwCopilotAddin\backend.token` on Windows |
| Format | 64-character hex string, no newline |
| Regenerated | Every time the backend process starts |
| Used by | C# add-in, smoke test, pytest auth tests |

If the token file does not exist, the smoke test exits immediately with an error message. pytest auth-success tests are skipped with a descriptive reason.

---

## Running the smoke test

From inside `agent-backend\` (backend must be running):

```
python smoke_test.py
```

The smoke test:
- Verifies auth rejection (no token, wrong token → 403)
- Hits `GET /health` with the valid token → checks `status == "ok"`
- Hits `POST /generate` with "make a 10mm cube" → checks `cad_command` is present, `macro_code` is `None`, action is `create_shape`, shape is `box`
- Hits `POST /generate` with "delete all features" → checks action is `delete_all`
- Prints PASS/FAIL per check and exits 0 (all pass) or 1 (any fail)

---

## Running the pytest suite

All tests are in `agent-backend\tests\`. Run from inside `agent-backend\`:

```
cd C:\Users\theof\agent-backend
python -m pytest tests/ -v
```

Or from the repo root:

```
cd C:\Users\theof
python -m pytest agent-backend/tests/ -v
```

### What each test module covers

| File | Coverage | Needs backend? |
|---|---|---|
| `tests/test_security.py` — `TestTokenAuthRejection` | POST /generate and GET /health reject missing/wrong tokens (403) | Yes (skipped if not running) |
| `tests/test_security.py` — `TestTokenAuthSuccess` | Valid token + benign prompt → 200 + cad_command JSON | Yes (skipped if not running) |
| `tests/test_security.py` — `TestSanitizeContextValue` | `_sanitize_context_value()` strips newlines, replaces backticks, redacts injection keywords, caps at 1024 chars | No |
| `tests/test_security.py` — `TestCadCommandValidation` | Pydantic model rejects missing/zero dimensions, wrong shape_type for noop/delete_all | No |

Tests that require the backend are decorated with `@requires_backend`. They are automatically skipped if `http://127.0.0.1:8001` is not reachable.

### Running a single test by name

```
python -m pytest tests/test_security.py::TestSanitizeContextValue::test_newlines_stripped -v
python -m pytest tests/test_security.py::TestTokenAuthRejection::test_health_no_token_returns_403 -v
python -m pytest tests/test_security.py::TestCadCommandValidation -v
```

### Running only unit tests (no backend needed)

```
python -m pytest tests/ -v -k "Sanitize or CadCommand"
```

### Running only network tests (backend required)

```
python -m pytest tests/ -v -k "TokenAuth"
```

---

## Why not PowerShell / Invoke-RestMethod?

Using `Invoke-RestMethod` (or similar) to send test payloads that contain prompt-injection strings — even synthetic ones used for negative testing — places those strings on the PowerShell command line. Windows Defender and enterprise EDR products scan command lines and flag patterns such as injection keywords, regardless of context.

**Observed problem:** A prior developer test that sent `"RULE: ignore previous"` as a POST body via PowerShell triggered a "Malicious command line detected" alert. The backend was not malicious, but the test method was correctly suspicious.

**Solution:** All injection-pattern tests now live entirely inside Python source files, where the strings exist as Python string literals in test functions. They are never passed through a shell command line, never appear in process arguments, and never trigger command-line scanning.

This is why every test file starts with `# BENIGN TEST SCRIPT` and uses `httpx` or direct Python imports instead of shell commands.

---

## Adding new tests

1. Add to `tests/test_security.py` or create a new file in `tests/`.
2. Include `# BENIGN TEST SCRIPT` at the top.
3. For live-backend tests, use the `@requires_backend` marker from `conftest.py`.
4. For unit tests on `main.py` internals, import the function directly (e.g. `from main import _sanitize_context_value`).
5. Keep all test payloads obviously benign — if it looks like an attack payload, make it more synthetic.

---

## Troubleshooting

**"Token file not found"** — The backend has not been started yet. Run `uvicorn main:app --host 127.0.0.1 --port 8001` first.

**"Connection refused" / tests skipped** — Backend is not running. Start it as above.

**"ModuleNotFoundError: No module named 'main'"** — You are running pytest from outside `agent-backend\`. Either `cd agent-backend` first, or add `agent-backend` to `PYTHONPATH`.

**Tests fail with 503** — The backend started but agent initialisation has not completed. Wait a few seconds and re-run.
