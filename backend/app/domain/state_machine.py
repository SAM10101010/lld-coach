"""Explicit evaluation state machine (no distributed queue in MVP).

DRAFT -> SUBMITTED -> EVALUATING -> COMPLETED
EVALUATING -> FAILED -> EVALUATING (retry)
"""

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
EVALUATING = "EVALUATING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

_ALLOWED: dict[str, set[str]] = {
    DRAFT: {SUBMITTED},
    SUBMITTED: {EVALUATING},
    EVALUATING: {COMPLETED, FAILED},
    FAILED: {EVALUATING},
    COMPLETED: set(),
}


class InvalidTransitionError(ValueError):
    pass


def can_transition(frm: str, to: str) -> bool:
    return to in _ALLOWED.get(frm, set())


def require_transition(frm: str, to: str) -> None:
    if not can_transition(frm, to):
        raise InvalidTransitionError(f"Invalid status transition: {frm} -> {to}")
