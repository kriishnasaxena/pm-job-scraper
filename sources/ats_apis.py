"""Company career pages hosted on Greenhouse, Lever and Ashby (public JSON APIs).

The company list lives in the sheet's "Companies" tab. For rows with ATS =
"auto", we try all three systems with the given slug and write back which
one worked (or "not-found"), so later runs only make one request.
"""
import time
from datetime import datetime, timezone

import requests

from core.models import Job

UA = {"User-Agent": "Mozilla/5.0 (pm-job-scraper; personal job search)"}


def _get(url):
    r = requests.get(url, headers=UA, timeout=25)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def _greenhouse(company, slug):
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true")
    if data is None or "jobs" not in data:
        return None
    return [Job(company=company, title=j.get("title", ""), url=j.get("absolute_url", ""),
                source="Greenhouse", location=(j.get("location") or {}).get("name", ""),
                description=j.get("content", ""),
                posted_at=(j.get("first_published") or j.get("updated_at") or "")[:10])
            for j in data["jobs"]]


def _lever(company, slug):
    data = _get(f"https://api.lever.co/v0/postings/{slug}?mode=json")
    if data is None or not isinstance(data, list):
        return None
    out = []
    for j in data:
        cats = j.get("categories") or {}
        lists = "\n".join(f"{l.get('text','')}\n{l.get('content','')}" for l in j.get("lists") or [])
        created = j.get("createdAt")
        out.append(Job(company=company, title=j.get("text", ""),
                       url=j.get("applyUrl") or j.get("hostedUrl", ""), source="Lever",
                       location=cats.get("location", "") or ", ".join(cats.get("allLocations") or []),
                       description=f"{j.get('descriptionPlain','')}\n{lists}\n{j.get('additionalPlain','')}",
                       posted_at=datetime.fromtimestamp(created / 1000, timezone.utc).strftime("%Y-%m-%d") if created else "",
                       job_type_hint=cats.get("commitment", "")))
    return out


def _ashby(company, slug):
    data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false")
    if data is None or "jobs" not in data:
        return None
    out = []
    for j in data["jobs"]:
        loc = j.get("location", "")
        if j.get("isRemote"):
            loc = f"{loc} (Remote)".strip()
        out.append(Job(company=company, title=j.get("title", ""),
                       url=j.get("applyUrl") or j.get("jobUrl", ""), source="Ashby", location=loc,
                       description=j.get("descriptionPlain", ""),
                       posted_at=(j.get("publishedAt") or "")[:10],
                       job_type_hint=j.get("employmentType", "")))
    return out


ATS = {"greenhouse": _greenhouse, "lever": _lever, "ashby": _ashby}


def fetch(cfg, ctx):
    store = ctx["store"]
    companies = store.read_companies()
    jobs, updates, errors = [], [], []
    for c in companies:
        if c["ats"] == "not-found":
            continue
        tried = [c["ats"]] if c["ats"] in ATS else list(ATS)
        found_ats, found = None, None
        for name in tried:
            try:
                res = ATS[name](c["company"], c["slug"])
            except Exception as e:  # network / bad JSON: report, keep going
                errors.append(f"{c['company']}/{name}: {e.__class__.__name__}")
                res = None
            if res is not None:
                found_ats, found = name, res
                break
            time.sleep(0.3)
        if found_ats is None:
            if c["ats"] == "auto":
                updates.append({"row": c["row"], "ats": "not-found", "status": "slug not found on Greenhouse/Lever/Ashby"})
            else:
                updates.append({"row": c["row"], "ats": c["ats"], "status": "error / not found"})
            continue
        jobs.extend(found)
        updates.append({"row": c["row"], "ats": found_ats, "status": f"ok ({len(found)} open roles)",
                        "matching": ""})
        c["_jobs"] = found
    ctx["company_updates"] = updates
    if errors:
        ctx.setdefault("warnings", []).extend(errors[:10])
    return jobs
