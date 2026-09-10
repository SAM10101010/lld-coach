"""Fixed evaluation rubric. A single reference solution is never the source of truth;
scores must be justified by evidence found in the learner submission."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Criterion:
    key: str
    name: str
    weight: int  # max points contributing to 0-100 overall
    description: str
    prompt_hint: str


RUBRIC: list[Criterion] = [
    Criterion(
        key="requirement_understanding",
        name="Requirement understanding",
        weight=20,
        description="Addresses stated requirements and makes assumptions explicit.",
        prompt_hint="Check each requirement is covered by some class/behavior; flag unaddressed requirements.",
    ),
    Criterion(
        key="responsibilities",
        name="Responsibilities",
        weight=20,
        description="Cohesive, appropriately assigned class responsibilities (SRP).",
        prompt_hint="Judge cohesion and SRP; point to god-classes or anemic classes.",
    ),
    Criterion(
        key="abstraction",
        name="Abstraction / interfaces",
        weight=15,
        description="Useful abstractions, encapsulation, no artificial layers.",
        prompt_hint="Reward encapsulation and polymorphism used for a reason; penalize abstraction for its own sake.",
    ),
    Criterion(
        key="extensibility",
        name="Extensibility",
        weight=15,
        description="Handles likely changes (new vehicle/spot/pricing, new floors, etc).",
        prompt_hint="Test against one concrete change: new type/strategy. Would it need shotgun surgery?",
    ),
    Criterion(
        key="relationships",
        name="Relationships",
        weight=10,
        description="Sensible association/composition/dependency and ownership.",
        prompt_hint="Check ownership (composition vs aggregation) and dependency direction.",
    ),
    Criterion(
        key="patterns",
        name="Patterns",
        weight=10,
        description="Patterns used appropriately, not for pattern-counting.",
        prompt_hint="Do NOT award points merely for naming patterns. Ask: does the pattern solve a real problem here?",
    ),
    Criterion(
        key="tradeoffs",
        name="Trade-offs / edge cases",
        weight=10,
        description="Explains choices and covers important failure scenarios.",
        prompt_hint="Look for explicit trade-offs and edge cases (concurrency, full lot, payment failure...).",
    ),
]

TOTAL_WEIGHT = sum(c.weight for c in RUBRIC)
assert TOTAL_WEIGHT == 100, f"Rubric weights must sum to 100, got {TOTAL_WEIGHT}"

# Structured text sections required for a meaningful attempt.
REQUIRED_SECTIONS = [
    "assumptions",
    "class_definitions",
    "relationships",
    "behaviors",
    "design_decisions",
    "tradeoffs",
    "edge_cases",
]

MIN_SECTION_CHARS = 20
MIN_SECTION_WORDS = 4
