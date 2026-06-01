# Sinas setup

## 1. Log into the instance
- Console (admin UI): `https://via-X.sinas.wearebrain.com:51245` (`SINAS_CONSOLE_URL`).
- Runtime/API: `https://via-X.sinas.wearebrain.com` (`SINAS_BASE_URL`).
- Replace `X` with your team's number. Log in with the email used for VIA signup
  (this run: `ali.erdogan.bilge@gmail.com`).

## 2. Create an admin API key
In the management console, create an admin API token (Management API, `/api/v1`).
Keep it secret. Verify it:
```bash
curl -s "$SINAS_BASE_URL/auth/me" -H "Authorization: Bearer $SINAS_ADMIN_TOKEN"
```

## 3. Configure .env
```bash
cp .env.example .env
# set SINAS_BASE_URL, SINAS_CONSOLE_URL, SINAS_ADMIN_TOKEN, SINAS_DEFAULT_MODEL
```
Never commit `.env` or `.sinas/config.json` (both gitignored).

## 4. Install the CLI and validate
The CLI needs **Node/npm** (not installed in the current dev box — install Node
first, or run from a machine that has it).
```bash
npm i -g @sinas/cli
sinas login                 # prompts instance_url + admin_token -> ./.sinas/config.json
sinas validate              # validates sinas-config.yaml + sinas-package.yaml
sinas preview
sinas install               # applies sinas-config.yaml (roles), then the package
sinas status
```
Fallback if the CLI is unavailable: validate/install via the Management API
(`POST /api/v1/packages/preview`, `POST /api/v1/packages/install`). See
docs/research/sinas-investigation.md.

## 5. Check the Claude provider + default model
```bash
curl -s "$SINAS_BASE_URL/api/v1/llm-providers/" \
  -H "Authorization: Bearer $SINAS_ADMIN_TOKEN"
```
Confirm a Claude provider exists and its default model is `claude-sonnet-4-6`.
If missing/mismatched, set it in the console and update `PRIMARY_LLM` /
agent `model` fields. (Do **not** create providers from the package.)

## 6. Python dependencies (uv)
```bash
uv venv
uv pip install -e ".[dev]"            # core + pytest
uv pip install -e ".[video,telegram]" # optional: opencv/scenedetect/telethon
```

## 7. Run diagnostics
```bash
# Local sanity check:
uv run python -c "import sys; sys.path[:0]=['functions','src']; \
import diagnose_runtime, json; print(json.dumps(diagnose_runtime.handler({}, {}), indent=2))"
# On the instance: execute clip2trace/diagnose_runtime and record output in
# docs/research/runtime-diagnostics.md.
```

## 8. Telegram secrets (live mode only)
```bash
export TELEGRAM_API_ID=... TELEGRAM_API_HASH=...   # from my.telegram.org
uv run python scripts/bootstrap_telegram_session.py   # prints StringSession
```
Store `TELEGRAM_API_ID/HASH/SESSION_STRING` as Sinas **secrets** and set
`ENABLE_TELEGRAM_LIVE_SEARCH=true`. Never commit them.
