"""Public HTML only. No account, private API, or access-challenge bypass."""
import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse, urlunparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

HOST = "https://justjoin.it"
LISTING = HOST + "/job-offers/all-locations/testing"


class SourceError(RuntimeError):
    pass


def canonical_url(value):
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "justjoin.it" or not parsed.path.startswith("/job-offer/"):
        raise SourceError("Unexpected job URL; refusing to follow another host")
    return urlunparse(("https", "justjoin.it", parsed.path.rstrip("/"), "", "", ""))


def documents(html):
    soup = BeautifulSoup(html, "html.parser")
    result = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except (ValueError, TypeError) as error:
            raise SourceError("Malformed structured data") from error
        values = data if isinstance(data, list) else [data]
        for item in values:
            result.extend(item.get("@graph", [item]))
    return soup, result


def listing_urls(html):
    _, docs = documents(html)
    for doc in docs:
        if doc.get("@type") == "CollectionPage":
            entity = doc.get("mainEntity", {})
            if entity.get("@type") == "ItemList":
                return list(dict.fromkeys(canonical_url(x["url"]) for x in entity.get("itemListElement", [])))
    raise SourceError("Public listing structure missing; collection may be blocked or the page changed")


def parse_job(html, url):
    soup, docs = documents(html)
    doc = next((x for x in docs if x.get("@type") == "JobPosting"), None)
    if not doc or not doc.get("title") or not doc.get("description"):
        raise SourceError("Full JobPosting data missing; login wall, removed listing, or source change")
    description = BeautifulSoup(doc["description"], "html.parser").get_text("\n", strip=True)
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    lines = list(soup.stripped_strings)
    # Restrict badges to the job header. Recommendations below the description
    # often describe other roles and must not contaminate experience or salary.
    end = lines.index("Job description") if "Job description" in lines else 0
    header = lines[max(0, end - 22):end]
    levels = [x.lower() for x in header if x.lower() in ("junior", "mid", "senior", "lead", "expert", "intern")]
    level = levels[-1] if levels else "unknown"
    mode = next((x.lower() for x in reversed(header) if x in ("Remote", "Hybrid", "Office")), "unknown")
    locations = doc.get("jobLocation", [])
    locations = locations if isinstance(locations, list) else [locations]
    addresses = [x.get("address", {}) for x in locations]
    countries = [x.get("addressCountry", "") for x in addresses]
    localities = [x.get("addressLocality", "") for x in addresses]
    applicant = doc.get("applicantLocationRequirements", {})
    applicants = applicant if isinstance(applicant, list) else [applicant]
    restrictions = [x.get("name", "") for x in applicants]
    salary = doc.get("baseSalary")
    contracts = [x for x in header if x in ("Permanent", "B2B", "Mandate", "Any", "Internship")]
    return {
        "source_id": canonical_url(url).rsplit("/", 1)[-1], "url": canonical_url(url),
        "title": doc["title"], "company": doc.get("hiringOrganization", {}).get("name", "Unknown employer"),
        "description": description,
        "details": {"level": level, "mode": mode, "countries": countries,
                    "locations": localities, "restrictions": restrictions,
                    "salary": salary, "contracts": contracts,
                    "salary_basis": list(dict.fromkeys(x for x in header if re.search(r"(?:Gross|Net) per", x, re.I))),
                    "posted_at": doc.get("datePosted"), "valid_through": doc.get("validThrough"),
                    "source": "Just Join IT", "category": "testing"},
    }


@asynccontextmanager
async def public_client():
    # Playwright's request client reads server-rendered public HTML without
    # downloading ads, scripts or images. No Chromium installation is needed.
    if os.getenv("SSL_CERT_FILE"):
        os.environ.setdefault("NODE_EXTRA_CA_CERTS", os.environ["SSL_CERT_FILE"])
    proxy_value = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    proxy = {"server": proxy_value} if proxy_value else None
    async with async_playwright() as playwright:
        client = await playwright.request.new_context(
            proxy=proxy, timeout=40000, user_agent="PersonalQAJobMonitor/0.1 (public job discovery)",
        )
        try:
            yield client
        finally:
            await client.dispose()


async def fetch(client, url):
    response = await client.get(url, max_redirects=3)
    if response.status != 200:
        raise SourceError(f"Source returned HTTP {response.status}; no access workaround attempted")
    if urlparse(response.url).netloc != "justjoin.it":
        raise SourceError("Unexpected source redirect")
    text = await response.text()
    if len(text) > 8_000_000:
        raise SourceError("Unexpectedly large source page")
    return text


async def collect(settings, on_job):
    errors, seen, page_fingerprints = [], set(), set()
    fetched = 0
    async with public_client() as client:
        robots_text = await fetch(client, HOST + "/robots.txt")
        robots = RobotFileParser()
        robots.parse(robots_text.splitlines())
        for page in range(1, settings.max_pages + 1):
            url = LISTING if page == 1 else f"{LISTING}?page={page}"
            if not robots.can_fetch("PersonalQAJobMonitor", url):
                raise SourceError("Source robots.txt disallows this listing path")
            await asyncio.sleep(settings.request_delay)
            try:
                urls = listing_urls(await fetch(client, url))
            except SourceError as error:
                errors.append(f"Listing page {page}: {error}")
                break
            fingerprint = tuple(urls)
            if fingerprint in page_fingerprints:
                errors.append("Pagination repeated a page; coverage limited to distinct pages retrieved")
                break
            page_fingerprints.add(fingerprint)
            if not urls:
                break
            for job_url in urls:
                if job_url in seen:
                    continue
                seen.add(job_url)
                if not robots.can_fetch("PersonalQAJobMonitor", job_url):
                    errors.append("Source robots.txt disallows a job detail path")
                    continue
                await asyncio.sleep(settings.request_delay)
                try:
                    html = await fetch(client, job_url)
                    on_job(parse_job(html, job_url))
                    fetched += 1
                except SourceError as error:
                    errors.append(f"{job_url}: {error}")
                    # Stop on an access challenge rather than hammering the source.
                    if "HTTP 403" in str(error) or "HTTP 429" in str(error):
                        return fetched, errors, len(seen)
                if len(seen) >= settings.max_jobs:
                    return fetched, errors, len(seen)
    return fetched, errors, len(seen)
