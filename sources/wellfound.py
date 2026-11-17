"""Wellfound (AngelList Talent) role pages, loaded in Scrapling's stealth
browser. Jobs live in the page's embedded Apollo cache."""
from datetime import datetime, timezone

from core.models import Job
from core.scrape import fetch_html, next_data


def parse(html: str) -> list[Job]:
    d = next_data(html)
    if not d:
        return []
    a = d.get("props", {}).get("pageProps", {}).get("apolloState", {}).get("data", {})
    company_of = {}
    for k, v in a.items():
        if k.startswith("StartupResult"):
            for ref in v.get("highlightedJobListings") or []:
                company_of[ref.get("__ref")] = v.get("name", "")
    out = []
    for k, v in a.items():
        if not k.startswith("JobListingSearchResult"):
            continue
        locs = ", ".join(v.get("locationNames") or [])
        if v.get("remote"):
            locs = (locs + " (Remote)").strip()
        ts = v.get("liveStartAt")
        posted = datetime.fromtimestamp(int(ts), timezone.utc).strftime("%Y-%m-%d") if ts else ""
        ymin = v.get("yearsExperienceMin")
        out.append(Job(
            company=company_of.get(k, ""), title=v.get("title", ""),
            url=f"https://wellfound.com/jobs/{v.get('id')}-{v.get('slug', '')}", source="Wellfound",
            location=locs, description=v.get("description", ""), posted_at=posted,
            experience=f"{ymin}+ yrs" if ymin not in (None, "") else "",
            job_type_hint=v.get("jobType", ""),
        ))
    return out


def fetch(cfg, ctx):
    sc = cfg["sources"]["wellfound"]
    jobs, errors, seen = [], [], set()
    for url in sc["urls"]:
        try:
            html = fetch_html(url, cfg, need_marker="apolloState", browser_first=True)
            found = parse(html)
        except Exception as e:
            errors.append(f"{url}: {str(e)[:120]}")
            continue
        if not found:
            errors.append(f"{url}: 0 jobs parsed (blocked or layout changed)")
        for j in found:
            if j.url not in seen:
                seen.add(j.url); jobs.append(j)
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs
