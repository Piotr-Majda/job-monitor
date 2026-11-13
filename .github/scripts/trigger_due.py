"""Invoke Render using GitHub OIDC; no database or email secrets in Actions."""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    app_url = os.environ["SCOUT_APP_URL"].rstrip("/")
    if not app_url.startswith("https://"):
        raise ValueError("SCOUT_APP_URL must use HTTPS")
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_url += ("&" if "?" in request_url else "?") + urllib.parse.urlencode({"audience": app_url})
    request = urllib.request.Request(request_url, headers={"Authorization": "Bearer " + os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]})
    with urllib.request.urlopen(request, timeout=30) as response:
        token = json.load(response)["value"]
    request = urllib.request.Request(app_url + "/internal/run-due", data=b"{}", method="POST",
                                    headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    complete = False
    with urllib.request.urlopen(request, timeout=150) as response:
        for line in response:
            if not line.strip():
                continue
            event = json.loads(line)
            status = event.get("status")
            print("Job monitor: " + str(status), flush=True)
            if status == "failed":
                return 1
            if status == "completed":
                complete = True
                if not event.get("email_configured"):
                    print("::notice::Email sender is not configured in Render; collection can run, but no digest can be sent.")
    return 0 if complete else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as error:
        stage = "GitHub identity issuance" if urllib.parse.urlparse(error.url).hostname == "token.actions.githubusercontent.com" else "Render scheduled invocation"
        print(f"{stage} returned HTTP {error.code}.", file=sys.stderr)
        try:
            detail = json.loads(error.read(4096)).get("detail", "")
            if isinstance(detail, str) and detail.startswith(("GitHub identity verification failed", "This workflow is not authorized", "Scheduled invocation is not configured", "A GitHub Actions identity token is required")):
                print(detail, file=sys.stderr)
        except (ValueError, AttributeError):
            pass
        raise SystemExit(1)
    except Exception as error:
        print(f"Scheduled invocation failed ({type(error).__name__}). No credentials were logged.", file=sys.stderr)
        raise SystemExit(1)
