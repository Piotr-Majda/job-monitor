"""Trust only the selected GitHub workflow's short-lived signed identity."""
import jwt
from fastapi import HTTPException
from jwt import PyJWKClient

from .config import settings

ISSUER = "https://token.actions.githubusercontent.com"
jwks = PyJWKClient(ISSUER + "/.well-known/jwks", cache_jwk_set=True, lifespan=300, timeout=15)


def verify_workflow_token(authorization):
    if not settings.scheduler_repository or not settings.scheduler_repository_id:
        raise HTTPException(503, "Scheduled invocation is not configured")
    if not authorization or not authorization.startswith("Bearer ") or len(authorization) > 16384:
        raise HTTPException(401, "A GitHub Actions identity token is required")
    token = authorization[7:]
    try:
        key = jwks.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=settings.app_url,
                            issuer=ISSUER, leeway=15,
                            options={"require": ["exp", "iat", "nbf", "sub", "jti"]})
    except jwt.PyJWTError:
        raise HTTPException(403, "GitHub identity verification failed") from None
    expected = settings.scheduler_repository
    if (claims.get("repository") != expected
            or str(claims.get("repository_id")) != settings.scheduler_repository_id
            or claims.get("ref") != "refs/heads/main"
            or claims.get("sub") != f"repo:{expected}:ref:refs/heads/main"
            or claims.get("workflow_ref") != f"{expected}/.github/workflows/job-monitor.yml@refs/heads/main"
            or claims.get("event_name") not in ("schedule", "workflow_dispatch")):
        raise HTTPException(403, "This workflow is not authorized")
    return claims
