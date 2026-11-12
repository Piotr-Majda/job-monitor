import re
from datetime import datetime, timezone


def assess(job, criteria):
    title, description, details = job.title, job.description, job.details
    reasons, concerns, exclusions = [], [], []
    text = title + "\n" + description
    for skill in criteria.get("skills", ["Python"]):
        if not re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", text, re.I):
            exclusions.append(f"Required skill absent: {skill}")
        else:
            lines = [line for line in description.splitlines() if re.search(r"(?<!\w)" + re.escape(skill) + r"(?!\w)", line, re.I)]
            evidence = lines[0] if lines else title
            position = evidence.lower().find(skill.lower())
            start = max(0, position - 80)
            reasons.append(f"{skill}: " + ("…" if start else "") + evidence[start:start + 240])
    automation = re.search(r"automat|pytest|selenium|playwright|robot framework", text, re.I)
    qa = re.search(r"\bqa\b|\btest|quality|weryfikac", text, re.I)
    if not automation or not qa:
        exclusions.append("No clear QA/test automation evidence")
    else:
        reasons.append("QA/test automation responsibilities found")
    level = details.get("level", "unknown")
    if re.search(r"\bsenior\b|\blead(?:er)?\b|\bprincipal\b|\bexpert\b|\barchitect\b|\bmanager\b", title, re.I):
        exclusions.append("Title indicates a senior or leadership role")
    elif level == "unknown":
        concerns.append("Seniority unknown; check experience requirements")
    elif level not in criteria.get("levels", ["junior", "mid"]):
        exclusions.append(f"Seniority outside profile: {level}")
    else:
        reasons.append(f"Source seniority: {level}")
    countries = [x.casefold() for x in details.get("countries", [])]
    restrictions = [x.casefold() for x in details.get("restrictions", [])]
    country = criteria.get("country", "PL")
    accepted_names = {"pl", "poland", "polska"} if country == "PL" else {country.casefold()}
    if countries and not any(x in accepted_names for x in countries):
        exclusions.append("Listed location is outside the profile country")
    elif restrictions and not any(x in accepted_names for x in restrictions):
        exclusions.append("Applicant location restriction does not establish eligibility in Poland")
    elif not countries and not restrictions:
        concerns.append("Country eligibility unknown")
    else:
        reasons.append("Location permits work in Poland; relocation accepted")
    if not details.get("salary"):
        concerns.append("Salary unknown; no salary minimum configured")
    expiry = details.get("valid_through")
    if expiry:
        try:
            if datetime.fromisoformat(expiry.replace("Z", "+00:00")).replace(tzinfo=None) < datetime.now(timezone.utc).replace(tzinfo=None):
                exclusions.append("Source closing date has passed")
        except ValueError:
            concerns.append("Closing date could not be interpreted")
    # Optional-skill sections are not reliably structured in public descriptions.
    # Keep a relevant Python mention eligible and expose evidence for review.
    concerns.append("Review experience and whether Python is required or optional")
    return {"eligible": not exclusions, "recommendation": "Recommended" if not exclusions and level != "unknown" else "Review" if not exclusions else "Outside profile",
            "reasons": reasons, "concerns": concerns, "exclusions": exclusions}
