"""Internshala listings, scraped with Scrapling (adaptive selectors).

Listing pages give title/company/location; the JD is fetched from each
job's detail page, but only for jobs that are new and pass the title filter.
"""
import re

from core.models import Job
from core.scrape import get_page, select, first_text, page_text

BASE = "https://internshala.com"
CARD_SELECTORS = ["div.individual_internship[internshipid]", "div.individual_internship",
                  "div.internship_meta", "div[id^='individual_internship_']"]
TITLE_SEL = ["h3.job-internship-name a", "a.job-title-href", "h3.heading_4_5 a", ".profile a", "h3 a", "h2 a"]
COMPANY_SEL = ["p.company-name", ".company-name", ".company_name a", ".company_name", ".link_display_like_text"]
LOCATION_SEL = [".locations a", ".row-1-item.locations span", ".location_link", ".locations"]
DETAIL_LINK_RE = re.compile(r"/(internship|job)/detail/[^\"'\s?#]+")


def _detail_url(card) -> str:
    for attr in ("data-href", "href"):
        v = card.attrib.get(attr)
        if v and "/detail/" in v:
            return v if v.startswith("http") else BASE + v
    for a in card.css("a"):
        h = a.attrib.get("href", "")
        if "/detail/" in h:
            return h if h.startswith("http") else BASE + h
    return ""


def _company_from_url(url: str) -> str:
    m = re.search(r"-at-(.+?)\d*$", url.rstrip("/"))
    return m.group(1).replace("-", " ").title() if m else ""


def fetch(cfg, ctx):
    sc = cfg["sources"]["internshala"]
    delay = cfg.get("request_delay", 1.5)
    jobs, seen, errors = [], set(), []
    for url in sc["urls"]:
        try:
            page = get_page(url, delay)
        except Exception as e:
            errors.append(f"{url}: {e}")
            continue
        is_job = "/jobs/" in url or "fresher-jobs" in url
        cards = select(page, CARD_SELECTORS, identifier="internshala_cards")
        found_here = 0
        for card in cards:
            durl = _detail_url(card)
            if not durl or durl in seen:
                continue
            seen.add(durl)
            title = first_text(card, TITLE_SEL)
            company = first_text(card, COMPANY_SEL) or _company_from_url(durl)
            location = first_text(card, LOCATION_SEL)
            posted = first_text(card, [".status-inactive", ".status-success", ".status-info",
                                       ".posted_by_container", "[class*='status']"])
            jobs.append(Job(company=company, title=title, url=durl, source="Internshala",
                            location=location, posted_at=posted,
                            job_type_hint="fulltime" if is_job else "internship"))
            found_here += 1
        # Fallback if card parsing found nothing: use detail links directly.
        if found_here == 0:
            for a in page.css("a"):
                h = a.attrib.get("href", "")
                if not DETAIL_LINK_RE.search(h):
                    continue
                durl = h if h.startswith("http") else BASE + h
                if durl in seen:
                    continue
                seen.add(durl)
                title = " ".join(a.get_all_text(strip=True).split())
                jobs.append(Job(company=_company_from_url(durl), title=title, url=durl,
                                source="Internshala", job_type_hint="fulltime" if is_job else "internship"))
                found_here += 1
        if found_here == 0:
            errors.append(f"{url}: 0 listings parsed (site layout may have changed)")
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs


def enrich(job: Job, cfg):
    """Fetch the detail page for the JD (and fill gaps)."""
    page = get_page(job.url, cfg.get("request_delay", 1.5))
    job.description = page_text(page, ["div.internship_details", "div.detail_view",
                                       "div#details_container", "div.text-container", "main"])
    if not job.location:
        job.location = first_text(page, LOCATION_SEL)
    if not job.company:
        job.company = first_text(page, COMPANY_SEL)
    m = re.search(r"Posted\s+([^\n]{1,30}ago|today|just now)", job.description, re.I)
    if m:
        job.posted_at = m.group(1)
