"""Evaluator abstraction (Change Test B) + concrete evaluators.

- `Evaluator` interface: practice flow depends on this, not on OpenAI.
- `RuleBasedEvaluator`: deterministic facts (sections, concepts, structure).
- `HeuristicEvaluator`: local stand-in that produces rubric-shaped,
  evidence-based feedback without any network call. Used when no API key
  is configured so the demo works offline.
- `LLMEvaluator`: OpenAI-backed judgment. Falls back to heuristic when no
  key is configured; raises EvaluatorError on transport/parse failure so
  the service can mark FAILED and preserve the submission.

Future `HumanEvaluator` / `StaticCodeEvaluator` implement `Evaluator`
without touching the practice flow.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class EvaluatorError(Exception):
    pass


@dataclass
class CriterionResult:
    name: str
    score: int
    max_score: int
    evidence: str
    concern: str
    suggestion: str
    confidence: float


@dataclass
class EvaluationResult:
    overall_score: int
    criteria: list[CriterionResult]
    strengths: list[str] = field(default_factory=list)
    improvements: list[dict] = field(default_factory=list)
    next_questions: list[str] = field(default_factory=list)
    provider: str = "rule"
    deterministic: dict = field(default_factory=dict)


class Evaluator(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def evaluate(self, problem: dict, submission) -> EvaluationResult:
        ...


# ---------------------------------------------------------------------------
# Deterministic evaluator
# ---------------------------------------------------------------------------
from .rubric import REQUIRED_SECTIONS, RUBRIC  # noqa: E402
from .submission import Submission  # noqa: E402


def _contains_any(haystack: str, keywords: list[str]) -> str | None:
    hay = haystack.lower()
    for kw in keywords:
        if kw.lower() in hay:
            return kw
    return None


class RuleBasedEvaluator(Evaluator):
    """Checks facts that need no LLM: sections, length, required concepts."""

    @property
    def name(self) -> str:
        return "rule"

    def evaluate(self, problem: dict, submission: Submission) -> EvaluationResult:
        sections = submission.sections()
        text = submission.combined_text()

        missing_sections: list[str] = []
        thin_sections: list[str] = []
        for key in REQUIRED_SECTIONS:
            val = (sections.get(key, "") or "").strip()
            if not val:
                missing_sections.append(key)
            elif len(val) < 20 or len(val.split()) < 4:
                thin_sections.append(key)

        required_concepts: list[dict] = problem.get("required_concepts", []) or []
        missing_concepts: list[dict] = []
        covered_concepts: list[str] = []
        for concept in required_concepts:
            cname = concept.get("concept", "")
            kws = concept.get("keywords", []) or []
            hit = _contains_any(text, kws) if kws else None
            if hit:
                covered_concepts.append(cname)
            else:
                missing_concepts.append({"concept": cname, "keywords": kws})

        # Structural signals (cheap, explainable)
        classes_text = sections.get("class_definitions", "")
        has_class_keyword = "class " in classes_text.lower() or "interface " in classes_text.lower()
        has_methods = "(" in classes_text and ")" in classes_text
        rel_text = sections.get("relationships", "").lower()
        has_relation_word = any(
            w in rel_text for w in ["associat", "compos", "aggregat", "depend", "inherit", "extends", "implements", "owns", "has-a", "is-a", "--", "->"]
        )

        checks = [
            {"check": "required_sections_present", "passed": not missing_sections, "detail": f"missing={missing_sections}" if missing_sections else "all 7 sections present"},
            {"check": "sections_meaningful", "passed": not thin_sections, "detail": f"thin={thin_sections}" if thin_sections else "all sections have substance"},
            {"check": "concepts_covered", "passed": not missing_concepts, "detail": f"covered {len(covered_concepts)}/{len(required_concepts)}; missing={[m['concept'] for m in missing_concepts]}"},
            {"check": "classes_mention_abstractions", "passed": has_class_keyword, "detail": "mentions class/interface" if has_class_keyword else "no 'class'/'interface' found in Classes section"},
            {"check": "methods_mentioned", "passed": has_methods, "detail": "method-like signatures present" if has_methods else "no method signatures detected"},
            {"check": "relationships_explicit", "passed": has_relation_word, "detail": "relationship vocabulary found" if has_relation_word else "relationships look vague"},
        ]

        # Deterministic sub-score 0-100 (used as 30% of merged score + penalty source)
        total_checks = len(checks)
        passed = sum(1 for c in checks if c["passed"])
        concept_ratio = (len(covered_concepts) / len(required_concepts)) if required_concepts else 1.0
        section_ratio = (len(REQUIRED_SECTIONS) - len(missing_sections) - 0.5 * len(thin_sections)) / len(REQUIRED_SECTIONS)
        section_ratio = max(0.0, min(1.0, section_ratio))
        deterministic_score = round(100 * (0.5 * (passed / total_checks) + 0.3 * concept_ratio + 0.2 * section_ratio))

        deterministic = {
            "score": deterministic_score,
            "checks": checks,
            "missing_sections": missing_sections,
            "thin_sections": thin_sections,
            "missing_concepts": missing_concepts,
            "covered_concepts": covered_concepts,
        }
        return EvaluationResult(
            overall_score=deterministic_score,
            criteria=[],
            strengths=[],
            improvements=[],
            next_questions=[],
            provider="rule",
            deterministic=deterministic,
        )


# ---------------------------------------------------------------------------
# Heuristic (offline LLM stand-in): evidence-based, rubric-shaped feedback
# ---------------------------------------------------------------------------
def _snippet(text: str, limit: int = 140) -> str:
    t = " ".join((text or "").split())
    if len(t) <= limit:
        return t
    return t[:limit].rsplit(" ", 1)[0] + "..."


class HeuristicEvaluator(Evaluator):
    """Generates structured, criterion-level feedback without network access.

    Scoring is transparent: each criterion starts from a base derived from
    relevant section length + keyword hits, capped by its weight. Every
    result carries evidence (a quote from the submission), a concern, a
    suggestion, and a modest confidence — never a bare number.
    """

    @property
    def name(self) -> str:
        return "heuristic"

    def evaluate(self, problem: dict, submission: Submission) -> EvaluationResult:
        sections = submission.sections()
        text = submission.combined_text()
        det = RuleBasedEvaluator().evaluate(problem, submission).deterministic

        def located(section_key: str) -> str:
            return _snippet(sections.get(section_key, ""))

        # Coverage helpers
        def hits(keywords: list[str]) -> int:
            return sum(1 for k in keywords if k.lower() in text)

        results: list[CriterionResult] = []

        # 1. Requirement understanding (20)
        reqs = problem.get("requirements", []) or []
        covered_reqs = 0
        for r in reqs:
            words = [w.strip(".,()").lower() for w in str(r).split() if len(w) > 4]
            if any(w in text for w in words[:6]):
                covered_reqs += 1
        req_ratio = (covered_reqs / len(reqs)) if reqs else 0.5
        s1 = round(20 * (0.35 + 0.65 * req_ratio))
        if det["missing_sections"]:
            s1 = min(s1, 12)
        results.append(CriterionResult(
            name="Requirement understanding", score=min(20, s1), max_score=20,
            evidence=f"Assumptions: '{located('assumptions')}' Behaviors: '{located('behaviors')}'",
            concern=f"Covers ~{covered_reqs}/{len(reqs)} requirements by keyword; missing concepts: {[m['concept'] for m in det['missing_concepts']]}" if det["missing_concepts"] else "Requirements broadly referenced; verify each requirement maps to a behavior.",
            suggestion="Add a 1-line traceability map: Requirement -> Class/Behavior that satisfies it.",
            confidence=0.65,
        ))

        # 2. Responsibilities (20)
        cls_len = len(sections.get("class_definitions", ""))
        has_sr = any(w in text for w in ["responsib", "single responsibility", "cohesion", "owns", "responsible"])
        s2 = 8 + min(8, cls_len // 250) + (4 if has_sr else 0)
        results.append(CriterionResult(
            name="Responsibilities", score=min(20, s2), max_score=20,
            evidence=f"Classes: '{located('class_definitions')}'",
            concern="Some classes may be doing too much (e.g. manager/god-class) or too little (anemic data holders)." if not has_sr else "Responsibilities stated but check for god-classes vs anemic models.",
            suggestion="For each class write one sentence: 'This class owns X and does NOT own Y.' Split any class with 'and' in its responsibility.",
            confidence=0.6,
        ))

        # 3. Abstraction / interfaces (15)
        abs_words = ["interface", "abstract", "polymorph", "encapsulat", "strategy", "factory", "private", "public api"]
        ah = hits(abs_words)
        s3 = min(15, 5 + ah * 2 + (2 if "interface " in text else 0))
        results.append(CriterionResult(
            name="Abstraction / interfaces", score=s3, max_score=15,
            evidence=f"Design decisions: '{located('design_decisions')}'",
            concern="Abstractions look generic; encapsulation boundaries unclear." if ah < 2 else "Abstractions present; confirm each one hides a real variation.",
            suggestion="Name the variation each interface hides (e.g. PricingStrategy hides fee rules). Remove any interface with a single impl and no likely second impl.",
            confidence=0.6,
        ))

        # 4. Extensibility (15)
        ext_words = ["extensib", "open-closed", "open/closed", "strategy", "plugin", "new vehicle", "new spot", "new pricing", "without modifying", "add "]
        eh = hits(ext_words)
        s4 = min(15, 5 + eh * 2)
        if det["missing_concepts"]:
            s4 = min(s4, 10)
        results.append(CriterionResult(
            name="Extensibility", score=s4, max_score=15,
            evidence=f"Trade-offs: '{located('tradeoffs')}' Edge cases: '{located('edge_cases')}'",
            concern="Unclear how a new type/strategy is added without editing core classes.",
            suggestion=f"Walk through one concrete change for {problem.get('title')}: add a new type with steps (new class? config? no core edits?). Prefer composition + Strategy for varying behavior.",
            confidence=0.62,
        ))

        # 5. Relationships (10)
        rel = sections.get("relationships", "")
        rel_rich = len(rel) > 120 and any(w in rel.lower() for w in ["compos", "aggregat", "associat", "depend", "owns", "1..", "1:*", "*", "multiplicity"])
        s5 = 7 if rel_rich else (4 if len(rel) > 40 else 2)
        results.append(CriterionResult(
            name="Relationships", score=s5, max_score=10,
            evidence=f"Relationships: '{located('relationships')}'",
            concern="Ownership/multiplicity not explicit; dependency direction unclear." if not rel_rich else "Relationships stated; double-check composition vs aggregation choices.",
            suggestion="Label each link: composition (owns lifecycle) vs aggregation vs dependency, plus multiplicity (1..*, 0..1).",
            confidence=0.58,
        ))

        # 6. Patterns (10) — never reward name-dropping alone
        pat_words = ["strategy", "factory", "observer", "state", "singleton", "repository", "facade", "adapter", "decorator"]
        ph = [p for p in pat_words if p in text]
        justified = any(w in text for w in ["because", "trade-off", "tradeoff", "instead of", "alternative"])
        s6 = min(10, (3 + len(ph) * 2 + (2 if justified else -1))) if ph else 4
        s6 = max(2, s6)
        results.append(CriterionResult(
            name="Patterns", score=s6, max_score=10,
            evidence=f"Patterns mentioned: {ph if ph else 'none'}. Decisions: '{located('design_decisions')}'",
            concern="Patterns named without justifying why they fit (or no patterns where one would help)." if not justified else "Patterns present; ensure each solves a stated problem.",
            suggestion="For each pattern: problem it solves -> why this pattern -> what you gave up. Remove any pattern that adds indirection without a second variation.",
            confidence=0.55,
        ))

        # 7. Trade-offs / edge cases (10)
        te = sections.get("tradeoffs", "") + " " + sections.get("edge_cases", "")
        te_len = len(te)
        edge_words = ["concurr", "thread", "race", "fail", "timeout", "full", "empty", "invalid", "duplicate", "edge", "trade"]
        th = hits(edge_words)
        s7 = min(10, 3 + te_len // 200 + th)
        results.append(CriterionResult(
            name="Trade-offs / edge cases", score=s7, max_score=10,
            evidence=f"Trade-offs: '{located('tradeoffs')}' Edge: '{located('edge_cases')}'",
            concern="Few concrete failure scenarios or explicit trade-offs." if th < 2 else "Some edge cases covered; check concurrency/failure paths.",
            suggestion="List 3 edge cases with handling: full/empty state, invalid input, concurrent access. State one trade-off you accepted and why.",
            confidence=0.6,
        ))

        llm_subtotal = sum(r.score for r in results)
        # Merge with deterministic: 70% judgment + 30% deterministic
        overall = round(0.7 * llm_subtotal + 0.3 * det["score"])
        # Hard caps for missing fundamentals so feedback stays honest
        if det["missing_sections"]:
            overall = min(overall, 55)
        if len(det["missing_concepts"]) >= 3:
            overall = min(overall, 50)
        overall = max(0, min(100, overall))

        strengths: list[str] = []
        improvements: list[dict] = []
        if det["covered_concepts"]:
            strengths.append(f"Covers core concepts: {', '.join(det['covered_concepts'][:4])}.")
        if len(sections.get("class_definitions", "")) > 300:
            strengths.append("Classes section is substantive with explicit abstractions.")
        if any(w in text for w in ["because", "trade-off", "tradeoff"]):
            strengths.append("Explains reasoning behind choices, not just structure.")
        if not strengths:
            strengths.append("Submission is structured across all required sections.")

        for r in sorted(results, key=lambda x: x.score / x.max_score)[:3]:
            sev = "high" if (r.score / r.max_score) < 0.5 else "medium"
            improvements.append({"severity": sev, "message": f"{r.name}: {r.suggestion}", "section": r.name})

        next_q = [
            f"What breaks in your {problem.get('title')} design if load doubles or two users act concurrently?",
            "Which class would you split first as requirements grow, and why?",
            "What would you remove from this design without losing correctness?",
        ]

        return EvaluationResult(
            overall_score=overall,
            criteria=results,
            strengths=strengths,
            improvements=improvements,
            next_questions=next_q,
            provider="heuristic",
            deterministic=det,
        )


# ---------------------------------------------------------------------------
# LLM evaluator (OpenAI- or OpenRouter-backed, strict JSON contract)
# ---------------------------------------------------------------------------
class LLMEvaluator(Evaluator):
    def __init__(
        self,
        model: str = "",
        api_key: str = "",
        timeout_s: int = 30,
        inner: Evaluator | None = None,
        base_url: str | None = None,
        provider: str = "openai",
        extra_headers: dict | None = None,
    ):
        self._model = model
        self._api_key = api_key
        self._timeout = timeout_s
        self._fallback = inner or HeuristicEvaluator()
        self._base_url = base_url
        self._provider = provider or "openai"
        self._headers = dict(extra_headers or {})

    @property
    def name(self) -> str:
        return "llm"

    def evaluate(self, problem: dict, submission: Submission) -> EvaluationResult:
        # No key -> honest offline mode (demo-safe), clearly labeled.
        if not self._api_key:
            res = self._fallback.evaluate(problem, submission)
            res.provider = "heuristic (no API key)"
            return res

        from ..ai.llm_client import call_llm_json  # lazy import for testability
        from ..ai.prompts import build_system_prompt, build_user_prompt

        payload = submission.sections()
        data = call_llm_json(
            build_system_prompt(),
            build_user_prompt(problem, payload),
            self._model,
            self._api_key,
            self._timeout,
            base_url=self._base_url,
            extra_headers=self._headers or None,
        )
        return _parse_llm_result(data, problem, submission, provider=self._provider)

    # Exposed for tests: parse + validate strict contract, merge deterministic.
    def parse(self, data: dict, problem: dict, submission: Submission) -> EvaluationResult:
        return _parse_llm_result(data, problem, submission, provider=self._provider)


def _parse_llm_result(data: dict, problem: dict, submission: Submission, provider: str = "openai") -> EvaluationResult:
    det = RuleBasedEvaluator().evaluate(problem, submission).deterministic
    try:
        overall = int(data.get("overallScore", -1))
        raw_criteria = data.get("criteria", [])
        strengths = list(data.get("strengths", []) or [])
        improvements = list(data.get("improvements", []) or [])
        next_q = list(data.get("nextQuestions", []) or [])
        if not isinstance(raw_criteria, list) or not raw_criteria:
            raise EvaluatorError("AI response missing 'criteria'")
        by_name = {c.name.lower(): c for c in RUBRIC}
        parsed: list[CriterionResult] = []
        total = 0
        for item in raw_criteria:
            nm = str(item.get("name", ""))
            key = next((k for k in by_name if k in nm.lower() or nm.lower() in k), None)
            if key is None:
                # try matching rubric names loosely
                raise EvaluatorError(f"AI returned unknown criterion: {nm!r}")
            ref = by_name[key]
            sc = int(item.get("score", -1))
            if sc < 0 or sc > ref.weight:
                raise EvaluatorError(f"AI score out of range for {ref.name}: {sc} (max {ref.weight})")
            conf = float(item.get("confidence", 0.5))
            parsed.append(CriterionResult(
                name=ref.name, score=sc, max_score=ref.weight,
                evidence=str(item.get("evidence", ""))[:600],
                concern=str(item.get("concern", ""))[:600],
                suggestion=str(item.get("suggestion", ""))[:600],
                confidence=max(0.0, min(1.0, conf)),
            ))
            total += sc
        # Enforce overall == sum(criteria) per contract (tolerate small drift by clamping)
        if overall < 0 or overall > 100:
            overall = total
        else:
            # If model drifts, prefer the verifiable sum but keep within 100
            if abs(overall - total) > 5:
                overall = total
        # Apply deterministic honesty caps
        if det["missing_sections"]:
            overall = min(overall, 55)
        overall = max(0, min(100, overall))

        # Normalize improvements to {severity,message,section}
        norm_impr: list[dict] = []
        for imp in improvements:
            if isinstance(imp, dict):
                norm_impr.append({
                    "severity": str(imp.get("severity", "medium")),
                    "message": str(imp.get("message", imp.get("suggestion", ""))),
                    "section": str(imp.get("section", "")),
                })
            else:
                norm_impr.append({"severity": "medium", "message": str(imp), "section": ""})

        return EvaluationResult(
            overall_score=overall,
            criteria=parsed,
            strengths=[str(s) for s in strengths][:8],
            improvements=norm_impr[:8],
            next_questions=[str(q) for q in next_q][:5],
            provider=provider,
            deterministic=det,
        )
    except EvaluatorError:
        raise
    except Exception as exc:
        raise EvaluatorError(f"AI response failed validation: {exc}") from exc
