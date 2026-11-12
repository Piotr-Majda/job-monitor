import pytest

from app.db import init_db, make_engine


@pytest.fixture
def db(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def job_data():
    return {
        "source_id": "example-qa-python-wroclaw-testing", "url": "https://justjoin.it/job-offer/example-qa-python-wroclaw-testing",
        "title": "Test Automation Engineer", "company": "Example", "description": "Develop automated tests with Python and Selenium.",
        "details": {"level": "mid", "countries": ["PL"], "locations": ["Wrocław"], "restrictions": ["Poland"], "mode": "hybrid", "salary": None, "contracts": [], "posted_at": None},
    }
