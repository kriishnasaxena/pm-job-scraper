"""Cutshort role pages. Each page embeds ~50 jobs (with JD, experience and
posted date) in Next.js data, so one request per page is enough. Fetched with
Scrapling; falls back to Scrapling's browser if the plain request is blocked."""
import json

from core.models import Job
from core.scrape import fetch_html, next_data


def parse(html: str) -> list[Job]:
    d = next_data(html)
    if not d:
        return []
    out = []
    for q in d.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", []):
        data = ((q.get("state") or {}).get("data") or {}).get("data") or {}
        for j in (data.get("pageData") or {}).get("jobs") or []:
            fact = j.get("jobFactSummary") or {}
            exp = j.get("expRange") or {}
            loc = j.get("locationsText") or ", ".join(j.get("locations") or [])
            if j.get("remoteType") and "remote_not" not in j["remoteType"]:
                loc = (loc + " (Remote)").strip()
            out.append(Job(
                company=(j.get("companyDetails") or {}).get("name") or fact.get("companyName", ""),
                title=j.get("headline", ""), url=j.get("publicUrl", ""), source="Cutshort",
                location=loc, description=j.get("sanitizedComment", ""),
                posted_at=(fact.get("postedDate") or "")[:10],
                experience=f"{exp.get('min')}-{exp.get('max')} yrs" if exp.get("min") is not None else "",
                job_type_hint=" ".join(j.get("roleTypes") or []),
            ))
    return out


def fetch(cfg, ctx):
    sc = cfg["sources"]["cutshort"]
    jobs, errors, seen = [], [], set()
    for url in sc["urls"]:
        try:
            html = fetch_html(url, cfg, need_marker="__NEXT_DATA__")
            found = parse(html)
        except Exception as e:
            errors.append(f"{url}: {str(e)[:120]}")
            continue
        if not found:
            errors.append(f"{url}: 0 jobs parsed (page layout may have changed)")
        for j in found:
            if j.url not in seen:
                seen.add(j.url); jobs.append(j)
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:2]))
    return jobs
