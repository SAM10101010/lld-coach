# AI_USAGE.md — 5 meaningful AI-assisted decisions

## 1. Hybrid evaluation instead of LLM-only scoring
- **AI suggested:** “Just prompt GPT for a 0–100 score with comments.”
- **Accepted:** Using an LLM for judgment-heavy dimensions (responsibilities, abstraction, extensibility).
- **Rejected/changed:** LLM as the sole grader. Added a `RuleBasedEvaluator` for facts (sections present, required concepts, structure signals, state transitions, idempotency) and made the LLM never the source of truth for those.
- **Why:** A bare score is inconsistent and unexplainable; deterministic checks are cheap, testable, and make failures (missing ticket/pricing concepts) undeniable. Merge formula + honesty caps keep the final score grounded.

## 2. Structured JSON feedback contract instead of free-form text
- **AI suggested:** Free-form “strengths and weaknesses” paragraph.
- **Accepted:** Fixed rubric (7 criteria, weights sum to 100) + strict schema `{overallScore, criteria[{name,score,evidence,concern,suggestion,confidence}], strengths, improvements, nextQuestions}` with validation (unknown criterion → error, out-of-range score → error, overall re-derived from sum).
- **Rejected:** Markdown/free text parsing.
- **Why:** Comparable across attempts/providers, renderable as criterion bars + evidence in UI, and testable (malformed → FAILED, not corrupt data).

## 3. `Evaluator` interface for future evaluation approaches
- **AI suggested:** A single `evaluate_with_openai()` function called from the route.
- **Accepted:** `Evaluator` ABC with `RuleBasedEvaluator`, `HeuristicEvaluator`, `LLMEvaluator` (and documented `HumanEvaluator`/`StaticCodeEvaluator` plug points); orchestration depends on the interface.
- **Rejected:** Route-level `if provider == "openai"` branching.
- **Why:** Change Test B — adding human review or static analysis must not rewrite the practice flow. Also makes unit tests hermetic (inject fake evaluators, no network).

## 4. `Submission` abstraction for future diagram/code formats
- **AI suggested:** Seven string columns passed straight from API to prompt.
- **Accepted:** `Submission` ABC (`get_type/validate/combined_text/sections`) + `StructuredTextSubmission`; services accept the interface.
- **Rejected:** Baking “7 text fields” into Attempt/service signatures.
- **Why:** Change Test A — a future `DiagramSubmission`/`CodeSubmission` plugs in behind the same flow. Validation lives with the format, not scattered in routes.

## 5. Lightweight explicit state machine instead of a distributed queue
- **AI suggested:** Celery + Redis + retries for “production-grade” evaluation.
- **Accepted:** The state insight (DRAFT→SUBMITTED→EVALUATING→COMPLETED/FAILED, persist-before-evaluate, idempotent submit, FAILED+retry) implemented with plain DB commits in a monolith.
- **Rejected:** Any broker/queue/K8s in MVP.
- **Why:** The assignment explicitly forbids turning this into a distributed-systems project. The UI already speaks the async contract (`EVALUATING` + polling + retry), so a worker can be extracted later without changing the learner flow — documented as the first scaling cut.
