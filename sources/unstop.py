"""Unstop internships + jobs via its public JSON API (newest first)."""
import time
from datetime import date, datetime

import requests

from core.models import Job

API = "https://unstop.com/api/public/opportunity/search-result"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
           "Accept": "application/json", "Referer": "https://unstop.com/internships"}


def _posted(item):
    raw = item.get("approved_date") or item.get("updated_at") or ""
    return raw[:10]


def _location(item):
    jd = item.get("jobDetail") or {}
    locs = jd.get("locations") or [l.get("city") for l in item.get("locations") or [] if l.get("city")]
    loc = ", ".join(l for l in locs if l)
    if (item.get("region") == "online" or jd.get("type") in ("wfh", "remote")) and "remote" not in loc.lower():
        loc = (loc + " (Remote)").strip() if loc else "Remote"
    return loc


def fetch(cfg, ctx):
    sc = cfg["sources"]["unstop"]
    max_age = cfg.get("max_age_days", 7)
    jobs, errors = [], []
    for kind in sc.get("kinds", ["internships", "jobs"]):
        for page in range(1, sc.get("max_pages", 8) + 1):
            params = {"opportunity": kind, "page": page, "per_page": sc.get("per_page", 18), "oppstatus": "open"}
            try:
                r = requests.get(API, params=params, headers=HEADERS, timeout=(5, 20))
                r.raise_for_status()
                items = (r.json().get("data") or {}).get("data") or []
            except Exception as e:
                errors.append(f"{kind} p{page}: {e.__class__.__name__} {str(e)[:80]}")
                break
            if not items:
                break
            too_old = 0
            for it in items:
                jd = it.get("jobDetail") or {}
                lo, hi = jd.get("min_experience"), jd.get("max_experience")
                exp = f"{lo}-{hi} yrs" if lo is not None and hi is not None else (f"{lo}+ yrs" if lo is not None else "")
                posted = _posted(it)
                try:
                    if (date.today() - datetime.strptime(posted, "%Y-%m-%d").date()).days > max_age:
                        too_old += 1
                except ValueError:
                    pass
                jobs.append(Job(
                    company=(it.get("organisation") or {}).get("name", ""),
                    title=it.get("title", ""),
                    url=it.get("seo_url") or f"https://unstop.com/{it.get('public_url', '')}",
                    source="Unstop", location=_location(it), description=it.get("details", ""),
                    posted_at=posted, experience=exp,
                    job_type_hint="internship" if kind == "internships" else jd.get("timing", ""),
                ))
            if too_old == len(items):   # whole page is older than the window: stop paging
                break
            time.sleep(1)
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs
