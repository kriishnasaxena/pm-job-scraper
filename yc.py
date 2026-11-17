"""YC startup jobs (ycombinator.com/jobs), scraped with Scrapling.

Most YC roles are US-based, so the location filter does a lot of work
here. Detail pages are fetched only for new jobs whose title matches.
"""
import re

from core.models import Job
from core.scrape import get_page, page_text

JOB_LINK_RE = re.compile(r"^/companies/([^/]+)/jobs/[A-Za-z0-9]+")
BASE = "https://www.ycombinator.com"


def fetch(cfg, ctx):
    sc = cfg["sources"]["yc"]
    delay = cfg.get("request_delay", 1.5)
    jobs, seen, errors = [], set(), []
    for url in sc["urls"]:
        try:
            page = get_page(url, delay)
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        n = 0
        for a in page.css("a[href^='/companies/']"):
            href = a.attrib.get("href", "")
            m = JOB_LINK_RE.match(href)
            if not m:
                continue
            title = " ".join(a.get_all_text(strip=True).split())
            durl = BASE + m.group(0)
            if not title or durl in seen:
                continue
            seen.add(durl)
            company = m.group(1).replace("-", " ").title()
            jobs.append(Job(company=company, title=title, url=durl, source="YC Startups"))
            n += 1
        if n == 0:
            errors.append(f"{url}: 0 listings parsed (site layout may have changed)")
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs


def enrich(job: Job, cfg):
    page = get_page(job.url, cfg.get("request_delay", 1.5))
    text = page_text(page, ["div.prose", "main", "article"])
    job.description = text
    # Location usually sits near the top, e.g. "Bengaluru, KA, IN" or "Remote (IN)"
    head = text[:1500]
    m = re.search(r"\n([^\n]*(?:Remote|India|, IN\b|Bengaluru|Bangalore|Mumbai|Delhi|Gurugram|Hyderabad|Pune|US|USA|San Francisco|New York)[^\n]*)\n", head)
    job.location = m.group(1).strip() if m else "Unknown (check JD)"
