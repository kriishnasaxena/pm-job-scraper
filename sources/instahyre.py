"""Instahyre via its public job_search API, filtered by job function."""
import time

import requests

from core.models import Job

API = "https://www.instahyre.com/api/v1/job_search"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
           "Accept": "application/json", "Referer": "https://www.instahyre.com/search-jobs/"}


def fetch(cfg, ctx):
    sc = cfg["sources"]["instahyre"]
    jobs, errors, seen = [], [], set()
    for fn in sc.get("job_functions", [11, 34]):
        for page in range(sc.get("max_pages", 3)):
            params = {"company_size": 0, "job_type": 0, "job_functions": fn,
                      "limit": 50, "offset": page * 50}
            try:
                r = requests.get(API, params=params, headers=HEADERS, timeout=(5, 20))
                r.raise_for_status()
                items = r.json().get("objects") or []
            except Exception as e:
                errors.append(f"function {fn} p{page}: {e.__class__.__name__} {str(e)[:80]}")
                break
            for it in items:
                if it.get("id") in seen:
                    continue
                seen.add(it.get("id"))
                emp = it.get("employer") or {}
                jobs.append(Job(company=emp.get("company_name", ""), title=it.get("title", ""),
                                url=it.get("public_url", ""), source="Instahyre",
                                location=it.get("locations", "")))
            if len(items) < 50:
                break
            time.sleep(1)
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs
