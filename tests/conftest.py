"""Shared pytest fixtures: isolated SQLite DB + TestClient (no network, no OpenAI)."""
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("AI_MODEL", "test-model")

from app import config  # noqa: E402
config.OPENAI_API_KEY = ""

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.seed import seed_db  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool, future=True
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    seed_db(session)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


GOOD_PARKING = {
    "assumptions": "Three floors with fifty spots each. Bike fits small and above, car fits compact and above, truck needs large. Hourly pricing with grace period. Concurrent entries need locking.",
    "classDefinitions": "class Vehicle { plate; type } class ParkingSpot { id; size; occupied } class ParkingFloor { spots } interface SpotAllocationStrategy { allocate() } class SmallestFitStrategy implements SpotAllocationStrategy class Ticket { id; entryTime } interface PricingStrategy { fee() } class HourlyPricing implements PricingStrategy class ParkingLot { enter(); exit() }",
    "relationships": "ParkingLot composition ParkingFloor 1..*. ParkingFloor composition ParkingSpot 1..*. Ticket association Vehicle. ParkingLot dependency SpotAllocationStrategy injected. ParkingLot dependency PricingStrategy injected.",
    "behaviors": "enter allocates smallest fitting spot and creates ticket. exit computes fee via pricing strategy and frees the spot. Full lot returns null and rejects entry.",
    "designDecisions": "Strategy pattern for allocation and pricing because both vary independently. Composition for vehicle sizes to avoid class explosion. Ticket by id for O(1) lookup.",
    "tradeoffs": "Linear scan is O(n) but simple for hundreds of spots; would index free spots at larger scale. Trade-off accepted for simplicity.",
    "edgeCases": "Full lot rejection, duplicate plate entry, invalid ticket on exit, concurrent race for last spot under lock, exit before entry clamped.",
}
