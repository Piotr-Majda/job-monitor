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
    except jwt.PyJWTError as error:
        raise HTTPException(403, "GitHub identity verification failed: " + type(error).__name__) from None
    expected = settings.scheduler_repository
    # GitHub permits custom subject templates. Authorize the explicit signed
    # repository ID/name, branch and workflow claims rather than assuming the
    # account uses GitHub's default subject string. `sub` remains required above.
    requirements = {"repository": expected, "repository_id": settings.scheduler_repository_id,
                    "ref": "refs/heads/main",
                    "workflow_ref": f"{expected}/.github/workflows/job-monitor.yml@refs/heads/main"}
    mismatches = [key for key, value in requirements.items() if str(claims.get(key)) != value]
    if claims.get("event_name") not in ("schedule", "workflow_dispatch"):
        mismatches.append("event_name")
    if mismatches:
        # Report claim names, never token contents or credentials.
        raise HTTPException(403, "This workflow is not authorized: " + ", ".join(mismatches))
    return claims
