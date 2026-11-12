import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import oidc, web, worker
from app.db import init_db


@pytest.fixture
def identity(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(oidc.settings, "scheduler_repository", "Piotr-Majda/job-monitor")
    monkeypatch.setattr(oidc.settings, "scheduler_repository_id", "1455285333")
    monkeypatch.setattr(oidc.settings, "app_url", "https://example.onrender.com")
    monkeypatch.setattr(oidc.jwks, "get_signing_key_from_jwt", lambda _: SimpleNamespace(key=private.public_key()))
    current = int(time.time())
    claims = {"iss": oidc.ISSUER, "aud": "https://example.onrender.com", "exp": current + 300,
              "iat": current, "nbf": current - 1, "jti": "test-identity",
              "sub": "repo:Piotr-Majda/job-monitor:ref:refs/heads/main",
              "repository": "Piotr-Majda/job-monitor", "repository_id": "1455285333", "ref": "refs/heads/main",
              "workflow_ref": "Piotr-Majda/job-monitor/.github/workflows/job-monitor.yml@refs/heads/main",
              "event_name": "workflow_dispatch"}
    def token(**overrides):
        return "Bearer " + jwt.encode({**claims, **overrides}, private, algorithm="RS256")
    return token


def test_expected_signed_workflow_is_accepted(identity):
    assert oidc.verify_workflow_token(identity())["repository_id"] == "1455285333"


@pytest.mark.parametrize("changes", [
    {"repository": "attacker/job-monitor"}, {"repository_id": "another-repo"},
    {"ref": "refs/heads/untrusted"}, {"workflow_ref": "Piotr-Majda/job-monitor/other.yml@refs/heads/main"},
    {"event_name": "pull_request"}, {"aud": "https://another-app.example"}, {"exp": 1},
])
def test_other_repositories_branches_workflows_and_expired_tokens_are_rejected(identity, changes):
    with pytest.raises(HTTPException) as error:
        oidc.verify_workflow_token(identity(**changes))
    assert error.value.status_code == 403


def test_anonymous_invocation_is_rejected(identity):
    with pytest.raises(HTTPException) as error:
        oidc.verify_workflow_token("")
    assert error.value.status_code == 401


def test_streamed_invocation_runs_once_without_dashboard_password(db, monkeypatch, identity):
    monkeypatch.setattr(web, "engine", db)
    monkeypatch.setattr(web, "init_db", lambda: init_db(db))
    monkeypatch.setattr(web.settings, "admin_password", "private-dashboard-password")
    calls = []
    async def tick():
        calls.append("tick")
    monkeypatch.setattr(worker, "tick", tick)
    with TestClient(web.app) as client:
        assert client.post("/internal/run-due").status_code == 401
        response = client.post("/internal/run-due", headers={"Authorization": identity()})
        assert response.status_code == 200 and '"status": "completed"' in response.text
    assert calls == ["tick"]
