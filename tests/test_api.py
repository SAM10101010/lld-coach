"""API + failure/edge-case tests using an isolated in-memory DB."""
from tests.conftest import GOOD_PARKING


def test_problems_seeded(client):
    r = client.get("/api/problems")
    assert r.status_code == 200
    ids = {p["id"] for p in r.json()}
    assert {"parking-lot", "elevator-system", "vending-machine"} <= ids


def test_start_attempt_creates_draft(client):
    r = client.post("/api/problems/parking-lot/attempts")
    assert r.status_code == 200
    assert r.json()["status"] == "DRAFT"


def test_save_draft_does_not_trigger_evaluation(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    r = client.put(f"/api/attempts/{a['id']}", json=GOOD_PARKING)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DRAFT"
    assert body["evaluation"] is None
    assert body["submission"]["class_definitions"].startswith("class Vehicle")


def test_submit_persists_then_completes(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    r = client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "COMPLETED"
    assert body["submission"] is not None  # persisted before evaluation
    ev = body["evaluation"]
    assert ev["overall_score"] is not None and 0 <= ev["overall_score"] <= 100
    assert len(ev["criterion_results"]) == 7
    assert ev["deterministic"]["checks"]


def test_submit_rejects_empty_and_short(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    r = client.post(f"/api/attempts/{a['id']}/submit", json={})
    assert r.status_code == 422
    short = {k: "x" for k in GOOD_PARKING}
    r2 = client.post(f"/api/attempts/{a['id']}/submit", json=short)
    assert r2.status_code == 422


def test_invalid_transition_rejected(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    # retry-evaluation on a DRAFT (never evaluated) must be rejected
    r = client.post(f"/api/attempts/{a['id']}/retry-evaluation")
    assert r.status_code == 409


def test_duplicate_submit_is_idempotent(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    first = client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING).json()
    second = client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING).json()
    assert first["status"] == "COMPLETED"
    assert second["status"] == "COMPLETED"
    assert first["evaluation"]["id"] == second["evaluation"]["id"], "no duplicate evaluations"
    assert first["submission"]["id"] == second["submission"]["id"], "no duplicate submissions"


def test_retry_creates_new_attempt_preserves_history(client):
    a = client.post("/api/problems/parking-lot/attempts").json()
    client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING)
    r = client.post(f"/api/attempts/{a['id']}/retry")
    assert r.status_code == 200
    new_id = r.json()["id"]
    assert new_id != a["id"]
    hist = client.get("/api/attempts?problem_id=parking-lot").json()
    ids = {h["id"] for h in hist}
    assert {a["id"], new_id} <= ids


def test_failed_evaluation_preserves_submission_and_retries(client, monkeypatch):
    import app.application.services as svc

    a = client.post("/api/problems/parking-lot/attempts").json()

    def boom(*args, **kwargs):
        from app.domain.evaluator import EvaluatorError
        raise EvaluatorError("simulated AI outage")

    monkeypatch.setattr(svc, "_run_evaluators", boom)
    r = client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "FAILED"
    assert body["submission"] is not None, "submission must survive AI failure"
    assert body["evaluation"]["status"] == "FAILED"

    # restore real evaluators, retry must succeed without new submission
    monkeypatch.undo()
    r2 = client.post(f"/api/attempts/{a['id']}/retry-evaluation")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["status"] == "COMPLETED"
    assert body2["submission"]["id"] == body["submission"]["id"]


def test_malformed_ai_response_becomes_failed_not_corrupt(client, monkeypatch):
    import app.application.services as svc
    from app.domain.evaluator import EvaluatorError

    a = client.post("/api/problems/parking-lot/attempts").json()

    class BadLLM:
        def evaluate(self, problem, submission):
            raise EvaluatorError("AI returned invalid JSON: Expecting value")

    monkeypatch.setattr(svc, "LLMEvaluator", lambda **kw: BadLLM())
    r = client.post(f"/api/attempts/{a['id']}/submit", json=GOOD_PARKING)
    assert r.json()["status"] == "FAILED"
    assert r.json()["evaluation"]["overall_score"] is None
    monkeypatch.undo()


def test_history_lists_attempts(client):
    a1 = client.post("/api/problems/vending-machine/attempts").json()
    client.post(f"/api/attempts/{a1['id']}/submit", json={
        "assumptions": "small machine with twenty slots and coins and notes and exact change mode assumed here",
        "classDefinitions": "class Product { code price qty } class Inventory { slots } interface PaymentMethod { insert } class CashPayment implements PaymentMethod class VendingMachine { select insertMoney dispense }",
        "relationships": "VendingMachine composition Inventory 1..1. VendingMachine dependency PaymentMethod injected. Dispenser association Inventory.",
        "behaviors": "select then pay then dispense then change. cancel refunds. exact change mode rejects large notes.",
        "designDecisions": "Payment interface for card later. Inventory separate from money. Explicit state enum.",
        "tradeoffs": "Greedy change optimal for canonical coins. Single dispense lock accepted for simplicity.",
        "edgeCases": "Insufficient funds topup, sold out refund, jam refund and out of service, invalid code error.",
    })
    hist = client.get("/api/attempts").json()
    assert any(h["id"] == a1["id"] for h in hist)
