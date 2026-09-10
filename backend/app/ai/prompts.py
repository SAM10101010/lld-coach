"""Prompts for the LLM evaluator. Fixed rubric + structured JSON contract."""
import json

from ..domain.rubric import RUBRIC


def build_system_prompt() -> str:
    lines = [
        "You are a senior software design reviewer grading a Low-Level Design (LLD) practice submission.",
        "There is NO single correct reference solution. Grade the evidence in the learner submission.",
        "Do NOT award points merely for naming design patterns; judge whether each pattern/abstraction solves a real problem.",
        "Be concrete: quote or paraphrase evidence from the submission for every criterion.",
        "Return ONLY valid JSON matching the requested schema. No markdown, no extra text.",
    ]
    return "\n".join(lines)


def build_user_prompt(problem: dict, submission: dict) -> str:
    rubric_desc = "\n".join(
        f"- {c.name} (max {c.weight}): {c.description} Hint: {c.prompt_hint}" for c in RUBRIC
    )
    schema = {
        "overallScore": 82,
        "criteria": [
            {
                "name": "Requirement understanding",
                "score": 16,
                "evidence": "quote or paraphrase from the submission",
                "concern": "what may be weak",
                "suggestion": "actionable improvement",
                "confidence": 0.7,
            }
        ],
        "strengths": ["concrete strength with evidence"],
        "improvements": [{"severity": "medium", "message": "what to fix and how", "section": "Responsibilities"}],
        "nextQuestions": ["a question that stretches the design"],
    }
    criterion_names = ", ".join(f"{c.name} (max {c.weight})" for c in RUBRIC)
    return f"""Problem: {problem.get('title')}
Description: {problem.get('description')}
Requirements:
{chr(10).join('- ' + r for r in problem.get('requirements', []))}
Constraints:
{chr(10).join('- ' + c for c in problem.get('constraints', []))}

Rubric (weights sum to 100):
{rubric_desc}

Learner submission sections:
{json.dumps(submission, indent=2, ensure_ascii=False)[:12000]}

Score each rubric criterion within its max. overallScore must equal the sum of criterion scores (clamped 0-100).
Cover all 7 criteria, using exactly these names with their max scores: {criterion_names}.
The numbers above are only a format example — replace EVERY value with your own judgment of THIS submission.
Respond with JSON only, matching this schema:
{json.dumps(schema, indent=2)}
"""
