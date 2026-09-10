"""Seed data: 3 LLD problems. Parking Lot is the deepest demo problem."""
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .models import ProblemModel

PROBLEMS: list[dict] = [
    {
        "id": "parking-lot",
        "title": "Parking Lot",
        "description": (
            "Design a parking lot system for a multi-floor commercial complex. Vehicles arrive, "
            "take a ticket on entry, park in a suitable spot, and pay on exit based on duration "
            "and vehicle type. The operator wants to add new vehicle/spot types and pricing "
            "strategies without rewriting the core allocation logic."
        ),
        "difficulty": "Intermediate",
        "requirements": [
            "Support multiple floors, each with a configurable set of parking spots.",
            "Support vehicle types Bike, Car and Truck with different spot size needs.",
            "Support spot types Small, Compact and Large with compatibility rules.",
            "Vehicle entry: allocate a suitable free spot and generate a ticket.",
            "Vehicle exit: free the spot and compute the fee from duration + vehicle/spot type.",
            "Pricing must be extensible (hourly, flat + hourly, weekend surcharge) without editing allocation code.",
            "Handle full-lot, invalid ticket, and duplicate entry edge cases.",
        ],
        "constraints": [
            "One vehicle occupies exactly one spot; one spot holds at most one vehicle.",
            "Allocation should prefer the smallest fitting spot (avoid wasting large spots).",
            "Fee calculation must be testable in isolation from entry/exit flow.",
            "Do not assume a relational DB; design plain classes and interfaces.",
        ],
        "evaluation_criteria": [
            {"name": "Requirement understanding", "weight": 20},
            {"name": "Responsibilities", "weight": 20},
            {"name": "Abstraction / interfaces", "weight": 15},
            {"name": "Extensibility", "weight": 15},
            {"name": "Relationships", "weight": 10},
            {"name": "Patterns", "weight": 10},
            {"name": "Trade-offs / edge cases", "weight": 10},
        ],
        "required_concepts": [
            {"concept": "spot allocation", "keywords": ["spot", "allocat", "assign", "floor"]},
            {"concept": "vehicle abstraction", "keywords": ["vehicle", "bike", "car", "truck"]},
            {"concept": "ticket", "keywords": ["ticket"]},
            {"concept": "pricing strategy", "keywords": ["pric", "fee", "fare", "strategy", "hourly"]},
            {"concept": "entry/exit flow", "keywords": ["entry", "exit", "enter", "gate"]},
        ],
        "estimated_minutes": 60,
    },
    {
        "id": "elevator-system",
        "title": "Elevator System",
        "description": (
            "Design the control logic for an office building with multiple elevators. Passengers "
            "request rides from floors and inside cabins. The system dispatches elevators, moves "
            "them efficiently, and opens/closes doors safely. The building may add elevators or "
            "change the dispatch strategy later."
        ),
        "difficulty": "Intermediate",
        "requirements": [
            "Support N elevators serving M floors with up/down hall buttons and in-cabin floor buttons.",
            "Dispatch an elevator per hall request using a stated scheduling strategy (e.g. SCAN/LOOK/nearest).",
            "Model elevator state: idle, moving up/down, doors open/closed, overloaded.",
            "Door safety: never move with doors open; reopen on obstruction.",
            "Support capacity limits and overload handling.",
            "Dispatch strategy must be swappable without editing elevator movement code.",
            "Handle all-requests-same-direction, power-out, and stuck-door edge cases at design level.",
        ],
        "constraints": [
            "One request is served by exactly one elevator (no double dispatch).",
            "Movement and dispatch responsibilities must be separated.",
            "State transitions must be explicit and testable.",
        ],
        "evaluation_criteria": [
            {"name": "Requirement understanding", "weight": 20},
            {"name": "Responsibilities", "weight": 20},
            {"name": "Abstraction / interfaces", "weight": 15},
            {"name": "Extensibility", "weight": 15},
            {"name": "Relationships", "weight": 10},
            {"name": "Patterns", "weight": 10},
            {"name": "Trade-offs / edge cases", "weight": 10},
        ],
        "required_concepts": [
            {"concept": "dispatch/scheduling", "keywords": ["dispatch", "schedul", "scan", "look", "nearest", "strategy"]},
            {"concept": "elevator state", "keywords": ["elevator", "state", "idle", "moving", "door"]},
            {"concept": "request model", "keywords": ["request", "button", "hall", "floor"]},
            {"concept": "direction", "keywords": ["direction", "up", "down"]},
            {"concept": "capacity", "keywords": ["capacity", "overload", "weight", "limit"]},
        ],
        "estimated_minutes": 60,
    },
    {
        "id": "vending-machine",
        "title": "Vending Machine",
        "description": (
            "Design a vending machine that sells snacks and drinks. Customers insert money, select "
            "a product, and receive the item plus change. Operators restock items and collect cash. "
            "The machine must support new products and payment methods without core rewrites."
        ),
        "difficulty": "Beginner",
        "requirements": [
            "Model products with code, name, price and quantity; support out-of-stock handling.",
            "Accept cash (coins/notes) and compute change; payment method must be abstracted.",
            "Dispense flow: select -> pay -> dispense -> return change, with cancellation + refund.",
            "Model machine states explicitly (idle, accepting money, dispensing, out of service).",
            "Support restock and cash-collection operator actions.",
            "Handle insufficient funds, sold-out mid-transaction, and exact-change-only cases.",
        ],
        "constraints": [
            "Money handling and inventory must be separate responsibilities.",
            "State transitions must be explicit (no scattered booleans).",
            "Adding a card/mobile payment must not rewrite the dispense logic.",
        ],
        "evaluation_criteria": [
            {"name": "Requirement understanding", "weight": 20},
            {"name": "Responsibilities", "weight": 20},
            {"name": "Abstraction / interfaces", "weight": 15},
            {"name": "Extensibility", "weight": 15},
            {"name": "Relationships", "weight": 10},
            {"name": "Patterns", "weight": 10},
            {"name": "Trade-offs / edge cases", "weight": 10},
        ],
        "required_concepts": [
            {"concept": "inventory", "keywords": ["inventory", "stock", "quantity", "product", "item"]},
            {"concept": "payment abstraction", "keywords": ["payment", "coin", "cash", "change", "card"]},
            {"concept": "dispense flow", "keywords": ["dispense", "select", "vend"]},
            {"concept": "state machine", "keywords": ["state", "idle", "dispensing"]},
            {"concept": "restock", "keywords": ["restock", "refill", "operator"]},
        ],
        "estimated_minutes": 45,
    },
]


def seed_db(session: Session | None = None) -> int:
    close = False
    if session is None:
        session = SessionLocal()
        close = True
    try:
        count = 0
        for p in PROBLEMS:
            existing = session.get(ProblemModel, p["id"])
            if existing is None:
                session.add(ProblemModel(**p))
                count += 1
            else:
                for k, v in p.items():
                    if k != "id":
                        setattr(existing, k, v)
        session.commit()
        return count
    finally:
        if close:
            session.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    seed_db()


if __name__ == "__main__":
    init_db()
    print("seeded")
