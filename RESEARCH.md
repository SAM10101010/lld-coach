# Research Note — LLD Practice (1–2 pages)

## 1. Learner problem
Low-Level Design is practiced by writing classes, responsibilities, and interactions for
problems like Parking Lot, Elevator, or Vending Machine — typically in interviews, on paper,
or in a doc. Learners report three recurring pains:

1. **No tight feedback loop.** You can finish a design and still not know if responsibilities
   are cohesive, abstractions earn their keep, or the design survives a new requirement
   (new vehicle type, new pricing rule, new floor).
2. **Many valid answers.** Two very different designs can both be good. A single reference
   solution therefore misleads; what matters is requirement coverage, coupling/cohesion,
   encapsulation, extensibility, and explained trade-offs.
3. **No retained evidence.** Attempts live in scattered docs/whiteboards, so learners cannot
   see whether they keep repeating the same weakness (e.g. god-classes, vague relationships,
   missing edge cases).

A meaningful attempt must therefore capture: assumptions, classes/interfaces with
responsibilities, relationships with ownership, key behaviors/flows, decisions + rejected
alternatives, trade-offs, and edge cases. That is the minimum evidence a reviewer needs.

## 2. Existing approaches (sampled ~2–3 hours)

| Tool / source | Practice workflow | Submission | Feedback | Learning loop | Gap |
|---|---|---|---|---|---|
| **Exponent / interview-prep LLD guides** (e.g. Parking Lot walkthroughs) | Read prompt → watch/read reference design | None (passive) | Reference solution only | None | Teaches one “correct” shape; no personal feedback |
| **AI interview copilots / ChatGPT-style review** (“review my LLD”) | Paste design → free-form chat | Free text/code | Fluent but inconsistent; score varies run to run, rarely cites evidence | None (chat history only) | Unconstrained prompt (“is this good?”) → unrepeatable, hard to compare attempts |
| **Algo/DSA judges (LeetCode-style) applied to design** | Submit code → hidden tests | Code only | Pass/fail tests | Score history | Tests check behavior, not responsibility assignment, coupling, or extensibility reasoning |
| **GitHub LLD repos / Awesome-LLD lists** | Browse sample solutions | N/A | Community stars/comments | None | Great for reading, not for deliberate practice with feedback |
| **Excalidraw / diagram tools + peer review (e.g. Pramp/peer mock)** | Draw → human reviews | Diagram + discussion | High quality but scarce, unscalable, rubric varies by reviewer | Weak (no structured history) | Best feedback, worst availability/consistency |

Community threads (r/ExperiencedDevs, interview-prep Discords) echo the same theme: learners
want *“tell me what specifically is weak and what to change next time”*, not a number.

## 3. Comparison summary
- **Workflow:** most tools stop at start/submit; few close the retry loop.
- **Submission:** text proves reasoning, code proves interfaces/coupling, diagrams prove
  structure. No single format dominates; text is the cheapest that still exposes all three.
- **Feedback:** reference-solution diff < rubric + evidence + suggestions. Scores without
  evidence do not transfer to the next problem.
- **Learning loop:** almost nobody tracks recurring weaknesses across attempts.

## 4. Product gap
No lightweight tool gives **explainable, repeatable, rubric-based feedback** on a structured
design *and* keeps attempt history so the learner can see improvement. AI chat gives fluency
without consistency; static guides give consistency without personalization.

## 5. Product direction — why LLD Coach
- **Structured text submission (7 sections):** smallest format that still exposes
  responsibilities, relationships, behavior, and judgment. No diagram editor or code sandbox
  in MVP keeps the 2-day scope honest while leaving a `Submission` seam for both later.
- **Hybrid evaluation:** deterministic checks for facts (sections present, required concepts,
  state transitions, idempotency) + LLM for judgment (cohesion, abstraction quality,
  extensibility, trade-offs). Deterministic parts never depend on the model; the model never
  decides facts.
- **Fixed rubric + structured JSON contract** (`criterion → score → evidence → concern →
  suggestion → confidence`) so feedback is comparable across attempts and providers.
- **Attempt history + Try Again** turns one-off solving into deliberate practice.
- **Explicit states** (DRAFT → SUBMITTED → EVALUATING → COMPLETED/FAILED) with
  persist-before-evaluate and retry paths, without any queue infrastructure.

## 6. MVP boundary (intentionally NOT built)
Microservices/K8s/queues, LMS features (courses, roles, analytics), OAuth, UML editor, code
execution sandbox, gamification, RAG/vector DB, fine-tuning. Each was cut because it does not
improve the core loop (choose → design → submit → feedback → retry) within two days.

## Sources (small, real)
- Exponent / Educative LLD walkthroughs (Parking Lot, Elevator) — reference-solution pattern.
- “Awesome Low Level Design” GitHub collections — sample-solution pattern.
- Peer-mock / Pramp-style human review — high-quality but scarce feedback pattern.
- OpenAI structured-output / JSON-mode docs — basis for the fixed evaluation contract.
- Martin, *Clean Architecture* / SOLID essays — rubric dimensions (SRP, DIP, boundaries).
