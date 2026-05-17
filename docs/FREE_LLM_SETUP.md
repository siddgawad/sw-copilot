# Free LLM Setup — Never Get Blocked By Quota

SW Copilot is built to run on **only free or open-source LLM providers**. You
never pay anyone for inference, and the app keeps working even when every
cloud provider hits quota.

This doc tells you how to set up the recommended chain in 5 minutes.

---

## TL;DR

```
.env (in agent-backend/):

LLM_PROVIDER=gemini
LLM_FALLBACK_CHAIN=groq,nim,openai_compat,ollama

GEMINI_API_KEY=AIza...        # free at https://aistudio.google.com/apikey
GROQ_API_KEY=gsk_...           # free at https://console.groq.com/keys
```

Then install Ollama locally and pull the coder model:

```powershell
# 1. Install Ollama (one-time, ~150 MB)
# Download from https://ollama.com/download

# 2. Pull the model (~4 GB, one-time)
ollama pull qwen2.5-coder:7b

# 3. Verify
ollama list
```

That's it. The app will now:
- Try Gemini first (1M tokens/minute free)
- Fall back to Groq (fast, generous daily quota)
- Fall back to NVIDIA NIM if NIM_API_KEY is set
- Fall back to any free OpenAI-compatible host (OpenRouter, etc.)
- Fall back to local Ollama — **never rate-limited, never quota'd, always works**

---

## All supported providers (all free)

### 1. Gemini (Google AI Studio) — RECOMMENDED PRIMARY

- **Free tier**: 1M tokens/minute, 1500 requests/day per project.
- **Get key**: https://aistudio.google.com/apikey (Google account required).
- **Models**: `gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`.
- **Config**:
  ```
  LLM_PROVIDER=gemini
  GEMINI_API_KEY=AIza...
  GEMINI_MODEL=gemini-2.0-flash
  ```

### 2. Groq Cloud — RECOMMENDED FAST FALLBACK

- **Free tier**: Daily token quota (~14,400 requests/day). Sub-second latency.
- **Get key**: https://console.groq.com/keys (GitHub login).
- **Models**: `llama-3.1-8b-instant`, `llama-3.3-70b-versatile`, `mixtral-8x7b-32768`.
- **Config**:
  ```
  GROQ_API_KEY=gsk_...
  GROQ_MODEL=llama-3.1-8b-instant
  ```

### 3. NVIDIA NIM — OPTIONAL CLOUD FALLBACK

- **Free tier**: 1000 calls/month per model.
- **Get key**: https://build.nvidia.com/ (NVIDIA developer account).
- **Models**: `meta/llama-3.1-70b-instruct`, `mistralai/mixtral-8x22b-instruct-v0.1`.
- **Config**:
  ```
  NIM_API_KEY=nvapi-...
  NIM_MODEL=meta/llama-3.1-70b-instruct
  ```

### 4. OpenAI-compatible host (OpenRouter free, HuggingFace TGI, LM Studio…) — UNIVERSAL ADAPTER

Lets you plug any OpenAI-compatible API into the fallback chain without code
changes. Useful for **OpenRouter's free models**, HuggingFace's serverless
endpoints, or a local llama.cpp / LM Studio server.

Example with OpenRouter's free Llama model:

```
OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPAT_API_KEY=sk-or-v1-...    # free at https://openrouter.ai/keys
OPENAI_COMPAT_MODEL=meta-llama/llama-3.3-70b-instruct:free
```

### 5. Ollama (local) — ALWAYS-AVAILABLE LAST RESORT

- **Free tier**: N/A — runs entirely on your machine. No internet needed.
- **Install**: https://ollama.com/download (Windows installer ~150 MB).
- **Pull a coder model** (~4 GB):
  ```powershell
  ollama pull qwen2.5-coder:7b
  ```
- **Config** (already the default):
  ```
  OLLAMA_BASE_URL=http://localhost:11434/v1
  OLLAMA_MODEL=qwen2.5-coder:7b
  ```
- **Recommended models** for OperationGraph generation (in order of accuracy):
  1. `qwen2.5-coder:7b` — best free-tier accuracy on structured JSON, 4 GB
  2. `qwen2.5-coder:14b` — better but slower, 8 GB
  3. `llama3.1:8b` — generalist fallback, 5 GB
  4. `phi3.5:3.8b` — fastest, smallest, lower accuracy, 2.5 GB

Ollama uses your GPU automatically (NVIDIA / AMD / Apple Silicon). If you
don't have a GPU, it falls back to CPU — slower but still works.

---

## How the fallback chain actually works

```
User prompt
   |
   v
Pattern Router (deterministic)  ----->  fast-path graph (no LLM, never fails)
   |  (no match)
   v
LLM Chain (tries each in order):
   gemini (primary)            ----->  if 429/quota, next
   groq                        ----->  if 429/quota, next
   nim                         ----->  if 429/quota, next
   openai_compat               ----->  if 429/quota, next
   ollama (local)              ----->  always responds (or returns clear error)
```

The chain is configured in `agent-backend/config.py`:

```python
llm_fallback_chain: str = "groq,nim,openai_compat,ollama"
```

`ollama` is **always appended at the end** unless you explicitly set
`LLM_DISABLE_OLLAMA_FALLBACK=1`. This guarantees that as long as Ollama is
running locally, the app never fails for quota reasons.

---

## Test that everything works

Hit `GET /status` (no auth required):

```powershell
Invoke-RestMethod http://127.0.0.1:8001/status
```

You'll see:
- Which providers have keys configured
- The exact fallback chain that will be tried
- Ollama install URL if you don't have it

---

## When Ollama is missing

If you don't install Ollama, the app will still work — but only as long as
your configured cloud providers have quota. Once all of them hit 429, the
app returns a clear error pointing you at `https://ollama.com/download` and
the exact pull command.

To install Ollama later, just download + `ollama pull qwen2.5-coder:7b` and
restart the backend. No config change required — Ollama is already in the
default fallback chain.

---

## What this gives you

| Scenario | What happens |
|---|---|
| Pattern-router-recognised prompt (box, holes, fillet, etc.) | No LLM call. Instant. |
| Gemini quota OK | Gemini answers in <2s. |
| Gemini exhausted, Groq OK | Falls to Groq, answers in <1s. |
| All cloud quotas exhausted, Ollama running | Falls to local Ollama, 2–10s. |
| All cloud quotas exhausted, Ollama not installed | Clear error with install link. |
| No API keys at all, Ollama running | Works end-to-end via Ollama only. |
| No internet at all, Ollama running | Works (pattern router + Ollama). |
