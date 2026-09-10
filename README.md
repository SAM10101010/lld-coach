# LLD Coach — practice Low-Level Design with explainable feedback

A focused 2-day MVP: choose a problem → design → submit → rubric feedback → history → retry.
Evaluates against a **rubric, not a reference solution**. Monolith: FastAPI + SQLite + static SPA.

## Why it exists
LLD practice is easy to start, hard to judge. LLD Coach captures the minimum meaningful
evidence (assumptions, classes, relationships, behaviors, decisions, trade-offs, edge cases),
checks facts deterministically, judges quality with a fixed-rubric LLM (offline heuristic when
no key), and keeps attempt history so learners improve instead of one-shot solving.

## Tech stack
- Backend: FastAPI + Pydantic + SQLAlchemy (SQLite file; `DATABASE_URL` switchable to Postgres)
- AI: OpenAI or OpenRouter (OpenAI-compatible) chat-completions, JSON mode, timeout; heuristic fallback labeled honestly
- Frontend: dependency-free SPA (`frontend/index.html` + `app.js`, Tailwind CDN) served by FastAPI
- Tests: pytest + FastAPI TestClient, hermetic (no network)

## Architecture overview
```
frontend/ (SPA) → /api/* → api/routes.py (thin) → application/services.py
  → domain/{submission,evaluator,rubric,state_machine} → SQLite
  → ai/{prompts,llm_client} (OpenAI, optional)
```
Key abstractions: `Submission` (today `StructuredTextSubmission`; seam for diagram/code) and
`Evaluator` (`RuleBased` + `LLMEvaluator`/`Heuristic`; seam for human/static). See `DESIGN.md`.

## Local setup
Prereqs: Python 3.11+.

```powershell
cd lld-coach
python -m pip install -r requirements.txt
copy .env.example .env   # optional; fill OPENAI_API_KEY or OPENROUTER_API_KEY to enable live AI
python backend/server.py # serves API + UI at http://127.0.0.1:8000/
```

OpenRouter example (`.env`):
```
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=<your-key>
AI_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
```

Open **http://127.0.0.1:8000/** → Problems → Parking Lot → Start Attempt.
“Load sample” fills a concise demo design; edit, Submit, read feedback, Try Again.

## Environment variables
| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./lldcoach.db` | SQLAlchemy URL (Postgres-ready) |
| `AI_PROVIDER` | `auto` | `auto` (OpenRouter key → OpenRouter, else OpenAI key → OpenAI, else heuristic) or `openai`/`openrouter`/`heuristic` |
| `OPENAI_API_KEY` | _(empty)_ | Enables live OpenAI LLM; empty → falls through to heuristic |
| `OPENROUTER_API_KEY` | _(empty)_ | Enables live OpenRouter LLM (OpenAI-compatible `https://openrouter.ai/api/v1`) |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | Override for proxies/mirrors |
| `AI_MODEL` | `gpt-4o-mini` | Model id (OpenAI id, or full OpenRouter id e.g. `nvidia/nemotron-3-ultra-550b-a55b:free`) |
| `AI_TIMEOUT_SECONDS` | `30` | LLM timeout; timeout → FAILED + retry, submission kept |
| `CORS_ORIGINS` | `*` | Allowed origins |

Never commit real secrets. `.env.example` documents the shape.

## Database setup / migrations
No migrations in MVP: tables auto-create on startup (`Base.metadata.create_all`) and problems
seed idempotently (`seed.py`). To reset: stop server, delete `lldcoach.db`, restart.

## How to run tests
```powershell
cd lld-coach
python -m pip install -r requirements.txt
python -m pytest -q
```
Covers: DRAFT creation, draft≠evaluate, persist-before-evaluate, transitions, deterministic
concept detection, strict LLM-JSON validation, malformed/timeout → FAILED with data preserved,
idempotent re-submit, retry-creates-new-attempt with history intact. All hermetic (OpenAI stubbed).

## How AI evaluation works
1. `RuleBasedEvaluator` scores facts → `deterministic{score,checks,missing_*,covered_*}`.
2. `LLMEvaluator` (or `HeuristicEvaluator` when no key) scores 7 rubric criteria with
   `evidence/concern/suggestion/confidence` each.
3. Merge: `overall = 0.7·judgment + 0.3·deterministic`, capped 55 on missing sections.
4. Any transport/parse failure → attempt `FAILED`, `error` stored, submission untouched, retry exposed.
Prompt + schema: `backend/app/ai/prompts.py`; transport: `ai/llm_client.py`; validation: `domain/evaluator.py::_parse_llm_result`.

## Known limitations
- Single demo learner (no auth); history is global.
- Sync evaluation (no worker); refresh-safe via persisted `EVALUATING`, but slow LLM blocks the HTTP worker.
- SQLite single-file; keyword concept checks are English-substring based.
- Static SPA, not React; Tailwind via CDN needs internet for pixel-perfect styling (app works offline, plainer).

## Future improvements
Background AI worker first; then auth + per-user history, Postgres + Alembic, idempotency keys,
prompt versioning + eval telemetry, React/Vite frontend, diagram/code submissions, human-review evaluator.

## 2-minute demo
1. Open library → **Parking Lot** (note rubric, not reference answer). 2. **Start Attempt → Load sample**,
   tweak a line. 3. **Submit** → watch `EVALUATING` → `COMPLETED` with deterministic checks + 7 criterion cards.
   4. Open one issue → evidence + suggestion. 5. **History** shows the attempt; **Try Again** keeps it and starts fresh.
   6. Point to `Evaluator` + `Submission` interfaces as the two extensibility seams.
