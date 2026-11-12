"""Runtime entrypoint, including an explicitly configured one-time migration."""
import json
import os
import sys


def main():
    destination = os.getenv("MIGRATION_TARGET_DATABASE_URL", "")
    if destination:
        try:
            from .migrate import migrate
            result = migrate(os.environ["DATABASE_URL"], destination)
            print("MIGRATION_VERIFIED " + json.dumps(result, sort_keys=True), flush=True)
        except Exception as error:
            print(f"Migration stopped ({type(error).__name__}); no cutover performed. Check source/destination configuration.", file=sys.stderr, flush=True)
            return 1
        # The replacement web process serves the target immediately. The old
        # process remains read-only until Render routes traffic to this one.
        os.environ["DATABASE_URL"] = destination
        os.environ["MIGRATION_READ_ONLY"] = "false"
    os.execvp("uvicorn", ["uvicorn", "app.web:app", "--host", "0.0.0.0", "--port", os.getenv("PORT", "8000"), "--proxy-headers"])


if __name__ == "__main__":
    raise SystemExit(main())
