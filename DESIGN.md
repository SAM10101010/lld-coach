# Design Note — LLD Coach MVP

## 1. Problem statement + MVP scope
Learners cannot tell whether an LLD is actually good and cannot track improvement.
MVP (2 days): 3 problems (Parking Lot deep, Elevator, Vending Machine) · one structured-text
practice flow · persist-before-evaluate submission · hybrid rubric evaluation · evidence-based
feedback · attempt history + retry. Out of scope: §5 of spec (queues, auth, LMS, UML editor,
sandbox, gamification, RAG).

## 2. User journey
```
Library → Detail (requirements/constraints/rubric) → Start Attempt (DRAFT)
  → Practice (7 sections, Save Draft) → Submit (validate → persist → EVALUATING)
  → Feedback (score + criteria + deterministic + suggestions) → History → Try Again (new attempt, old kept)
```

## 3. Architecture
Simple monolith (FastAPI serves JSON API + static SPA; SQLite via SQLAlchemy):

```
browser (index.html/app.js)
   │  REST /api/*
   ▼
FastAPI routes (api/routes.py — thin)
   │  calls
   ▼
application/services.py (attempt lifecycle + evaluation orchestration)
   ├── domain/submission.py  (Submission interface + StructuredTextSubmission)
   ├── domain/evaluator.py   (Evaluator interface + RuleBased + Heuristic + LLMEvaluator)
   ├── domain/rubric.py      (7 criteria, weights sum to 100)
   └── domain/state_machine.py (DRAFT→SUBMITTED→EVALUATING→COMPLETED/FAILED)
   ▼
SQLAlchemy models (Problem/Attempt/Submission/Evaluation) → SQLite file
   ▼ (optional) OpenAI chat-completions, JSON mode, timeout
```

## 4. Domain model / classes & responsibilities
| Class | Owns | Does NOT own |
|---|---|---|
| `Problem` (row + seed dict) | Statement, requirements, constraints, required concepts, rubric ref | Grading logic |
| `Attempt` | Lifecycle status for one practice try | Solution content, scores |
| `Submission : Submission` | Solution content for one format; `validate()`, `combined_text()` | Evaluation, transport |
| `Evaluation` | Merged result: scores, evidence, deterministic detail, provider, error | Running evaluators |
| `RuleBasedEvaluator : Evaluator` | Deterministic facts: sections, concepts, structure signals | Any quality judgment |
| `HeuristicEvaluator : Evaluator` | Offline rubric-shaped feedback with evidence templates | Network/API calls |
| `LLMEvaluator : Evaluator` | OpenAI fixed-rubric judgment + strict JSON parse/validation | Deterministic facts |
| `services` | Orchestration: persist-first, transitions, merge, idempotency, FAILED handling | HTTP, SQL specifics beyond ORM |

`Attempt` never touches OpenAI; routes never contain grading logic.

## 5. Submission abstraction (Change Test A)
```python
class Submission(ABC):
    def get_type(self): ...
    def validate(self) -> list[str]: ...
    def combined_text(self) -> str: ...
    def sections(self) -> dict: ...
```
`StructuredTextSubmission` implements it today. A future `DiagramSubmission(nodes, edges, notes)`
or `CodeSubmission(files)` implements the same four methods; `save_draft`/`submit_and_evaluate`
take a `Submission`, so the practice flow is unchanged — only a factory branch + table columns
are added.

## 6. Evaluator abstraction (Change Test B)
```python
class Evaluator(ABC):
    @property
    def name(self): ...
    def evaluate(self, problem, submission) -> EvaluationResult: ...
```
`RuleBasedEvaluator`, `HeuristicEvaluator`, `LLMEvaluator` implement it. A future
`HumanEvaluator` (queue + reviewer UI) or `StaticCodeEvaluator` (compile/AST checks) is a new
class registered in `_run_evaluators` — no route/flow rewrite. `EvaluationResult` is provider-neutral.

## 7. Deterministic vs AI split
| Deterministic (`RuleBasedEvaluator`) | AI (`LLMEvaluator` / heuristic stand-in) |
|---|---|
| Sections present + meaningful length | Responsibility cohesion, SRP violations |
| Problem concepts covered (keyword hit) | Coupling/cohesion, encapsulation quality |
| Class/method/relationship signals | Extensibility under a concrete change |
| State-transition validity, idempotency | Trade-offs, edge cases, explanation quality, suggestions |
| Produces `deterministic{score,checks,…}` | Produces 7 criterion results + strengths/improvements/questions |

Merge: `overall = round(0.7·judgment + 0.3·deterministic)`, capped at 55 if sections missing
(50 if ≥3 concepts missing) so feedback stays honest. Deterministic detail is always shown
separately — the LLM never decides facts.

## 8. Evaluation state machine
```
DRAFT --submit--> SUBMITTED --start--> EVALUATING --ok--> COMPLETED
                                        \--err--> FAILED --retry--> EVALUATING
```
Commits happen at each edge; submission row is written before `SUBMITTED`. Refresh mid-eval
sees `EVALUATING`; `POST …/retry-evaluation` resumes `FAILED`. Duplicate submit on
`EVALUATING`/`COMPLETED` returns current state (no duplicate rows).

## 9. DB model
`problems(id, title, description, difficulty, requirements[], constraints[], evaluation_criteria[], required_concepts[], estimated_minutes)` ·
`attempts(id, problem_id→problems, status, created_at, submitted_at)` ·
`submissions(id, attempt_id unique→attempts, type + 7 text fields)` ·
`evaluations(id, attempt_id unique→attempts, status, overall_score?, provider, criterion_results[], strengths[], improvements[], next_questions[], deterministic{}, error?)`.
No users table in MVP (single demo learner); add later without touching evaluation.

## 10. API overview
`GET /api/problems`, `GET /api/problems/{id}`, `POST /api/problems/{id}/attempts`,
`GET /api/attempts?problem_id=`, `GET /api/attempts/{id}`, `PUT /api/attempts/{id}` (draft),
`POST /api/attempts/{id}/submit`, `GET /api/attempts/{id}/evaluation`,
`POST /api/attempts/{id}/retry-evaluation`, `POST /api/attempts/{id}/retry`.
Validation errors → 422 with section messages; bad transitions → 409; unknown ids → 404.

## 11. Change tests
- **A (diagram submit):** add `DiagramSubmission implements Submission` + factory case;Attempt/Evaluation/services untouched.
- **B (human/static evaluator):** add `HumanEvaluator implements Evaluator`; orchestration calls it through the interface; FAILED/retry path reused.

## 12. Failure handling
Empty/short → 422 before persistence change. AI timeout/malformed → `FAILED` + `error` stored,
submission + deterministic checks kept, retry exposed. DB write failure → request 500, prior
committed state intact. Duplicate submit → idempotent return. Refresh during eval → persisted
`EVALUATING` + retry path.

## 13. Key trade-offs
- **SQLite over Postgres:** zero-ops demo; `DATABASE_URL` switch + same SQLAlchemy models migrate cleanly.
- **Sync evaluation over queue:** correct for MVP latency (heuristic <1s, OpenAI ~10s); first extraction at scale would be a background worker + `EVALUATING` polling (already the UI contract).
- **Static SPA over React build:** no build step → clean-checkout runnable; React/Vite can replace `frontend/` without API change.
- **Heuristic fallback when no key:** demo never dead-ends; provider label is honest (`heuristic (no API key)` vs `openai`).
- **No auth:** single-learner scope; attempts are the security boundary for now.

## 14. Limitations → at larger scale
Add Postgres + Alembic, background worker (Celery/RQ) for AI calls, auth + per-user history,
rate limiting + idempotency keys, prompt versioning + eval telemetry, React frontend if the UI
grows. First component to extract: the AI evaluation worker (slow, retryable, independently scalable).
