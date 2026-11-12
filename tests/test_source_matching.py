import copy
import json
from types import SimpleNamespace

import pytest

from app.matching import assess
from app.source import SourceError, canonical_url, listing_urls, parse_job


def page(doc, header="Mid Hybrid"):
    return '<script type="application/ld+json">' + json.dumps(doc) + '</script><div>' + header.replace(" ", "</div><div>") + '</div><h2>Job description</h2><p>Description</p><p>Senior</p><p>Office</p>'


def test_parser_uses_job_not_similar_offer_badges():
    doc = {"@type": "JobPosting", "title": "QA Python", "description": "<p>Write automated Python tests.</p>", "jobLocation": {"address": {"addressCountry": "pl", "addressLocality": "Wrocław"}}, "hiringOrganization": {"name": "Real employer"}}
    job = parse_job(page(doc), "https://justjoin.it/job-offer/a?tracking=x")
    assert job["details"]["level"] == "mid"
    assert job["details"]["mode"] == "hybrid"
    assert job["description"] == "Write automated Python tests."
    assert job["details"]["salary"] is None
    assert job["url"] == "https://justjoin.it/job-offer/a"


def test_source_fails_closed_on_schema_change_or_login_wall():
    with pytest.raises(SourceError):
        listing_urls("<h1>Sign in</h1>")
    with pytest.raises(SourceError):
        parse_job("<h1>Removed</h1>", "https://justjoin.it/job-offer/a")
    with pytest.raises(SourceError):
        canonical_url("https://evil.example/job-offer/a")


def test_listing_deduplicates_and_removes_tracking():
    doc = {"@type": "CollectionPage", "mainEntity": {"@type": "ItemList", "itemListElement": [{"url": "https://justjoin.it/job-offer/a?tracking=1"}, {"url": "https://justjoin.it/job-offer/a"}]}}
    assert listing_urls(page(doc)) == ["https://justjoin.it/job-offer/a"]


@pytest.mark.parametrize("country", ["PL", "pl", "Poland", "Polska"])
def test_poland_case_and_unknown_salary_remain_eligible(job_data, country):
    job_data["details"]["countries"] = [country]
    result = assess(SimpleNamespace(**job_data), {"skills": ["Python"], "levels": ["junior", "mid"]})
    assert result["eligible"]
    assert any("Salary unknown" in x for x in result["concerns"])


@pytest.mark.parametrize("title", ["Senior QA", "QA Leader", "QA Lead", "Test Automation Architect", "QA Manager"])
def test_leadership_is_not_recommended_for_junior_mid(job_data, title):
    job_data["title"] = title
    assert not assess(SimpleNamespace(**job_data), {})["eligible"]


def test_requires_python_and_poland_and_current_listing(job_data):
    job = SimpleNamespace(**copy.deepcopy(job_data))
    job.description = "Automated Java tests"
    assert not assess(job, {})["eligible"]
    job = SimpleNamespace(**copy.deepcopy(job_data))
    job.details["countries"] = ["DE"]
    assert not assess(job, {})["eligible"]
    job = SimpleNamespace(**copy.deepcopy(job_data))
    job.details["valid_through"] = "2000-01-01T00:00:00Z"
    assert not assess(job, {})["eligible"]
