"""Submission abstraction (Change Test A).

The practice flow depends only on the `Submission` interface, never on a
concrete format. Today we ship `StructuredTextSubmission`. Tomorrow a
`DiagramSubmission` or `CodeSubmission` can implement the same interface
without rewriting Attempt handling.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .rubric import MIN_SECTION_CHARS, MIN_SECTION_WORDS, REQUIRED_SECTIONS


class Submission(ABC):
    @abstractmethod
    def get_type(self) -> str:
        ...

    @abstractmethod
    def validate(self) -> list[str]:
        """Return human-readable validation errors (empty = valid)."""
        ...

    @abstractmethod
    def combined_text(self) -> str:
        """Lower-cased searchable text used by deterministic checks."""
        ...

    @abstractmethod
    def sections(self) -> dict[str, str]:
        ...


def _meaningful(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < MIN_SECTION_CHARS:
        return False
    return len(t.split()) >= MIN_SECTION_WORDS


@dataclass
class StructuredTextSubmission(Submission):
    assumptions: str = ""
    class_definitions: str = ""
    relationships: str = ""
    behaviors: str = ""
    design_decisions: str = ""
    tradeoffs: str = ""
    edge_cases: str = ""
    extra: dict = field(default_factory=dict)

    def get_type(self) -> str:
        return "structured_text"

    def sections(self) -> dict[str, str]:
        return {
            "assumptions": self.assumptions or "",
            "class_definitions": self.class_definitions or "",
            "relationships": self.relationships or "",
            "behaviors": self.behaviors or "",
            "design_decisions": self.design_decisions or "",
            "tradeoffs": self.tradeoffs or "",
            "edge_cases": self.edge_cases or "",
        }

    def validate(self) -> list[str]:
        errors: list[str] = []
        for key in REQUIRED_SECTIONS:
            value = self.sections().get(key, "")
            if not (value or "").strip():
                errors.append(f"Section '{key}' is required.")
            elif not _meaningful(value):
                errors.append(
                    f"Section '{key}' is too short: write at least "
                    f"{MIN_SECTION_CHARS} characters / {MIN_SECTION_WORDS} words explaining your design."
                )
        return errors

    def combined_text(self) -> str:
        return "\n".join(self.sections().values()).lower()


# Example of how a future format plugs in without touching the practice flow:
# @dataclass
# class DiagramSubmission(Submission):
#     nodes: list = field(default_factory=list)
#     edges: list = field(default_factory=list)
#     notes: str = ""
#     def get_type(self): return "class_diagram"
#     def validate(self): ...
#     def combined_text(self): ...
#     def sections(self): ...


def submission_from_dict(payload: dict, sub_type: str = "structured_text") -> Submission:
    if sub_type not in ("structured_text", "text", "structured-text"):
        raise ValueError(f"Unsupported submission type: {sub_type}")

    def pick(snake: str, camel: str) -> str:
        return payload.get(snake, payload.get(camel, "")) or ""

    return StructuredTextSubmission(
        assumptions=pick("assumptions", "assumptions"),
        class_definitions=pick("class_definitions", "classDefinitions"),
        relationships=pick("relationships", "relationships"),
        behaviors=pick("behaviors", "behaviors"),
        design_decisions=pick("design_decisions", "designDecisions"),
        tradeoffs=pick("tradeoffs", "tradeoffs"),
        edge_cases=pick("edge_cases", "edgeCases"),
    )
