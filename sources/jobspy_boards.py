"""LinkedIn, Naukri and Indeed via the open-source JobSpy library (no login used)."""
import time

from core.models import Job


def _val(row, key):
    v = row.get(key)
    if v is None:
        return ""
    try:
        import math
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass
    return str(v)


def fetch(cfg, ctx):
    from jobspy import scrape_jobs

    sc = cfg["sources"]["jobspy"]
    jobs, errors = [], []
    deadline = time.time() + 60 * sc.get("max_minutes", 10)
    for site in sc["sites"]:
        for term in sc["search_terms"]:
            if time.time() > deadline:
                errors.append(f"time budget hit before {site} '{term}' (raise max_minutes in config)")
                break
            print(f"  jobspy {site}: {term}", flush=True)
            kwargs = dict(
                site_name=[site],
                search_term=term,
                location=sc.get("location", "India"),
                results_wanted=sc.get("results_per_term", 25),
                hours_old=sc.get("hours_old", 3),
                country_indeed="India",
                description_format="markdown",
                verbose=0,
            )
            if site == "linkedin":
                kwargs["linkedin_fetch_description"] = sc.get("linkedin_fetch_description", True)
            try:
                df = scrape_jobs(**kwargs)
            except Exception as e:
                errors.append(f"{site} '{term}': {str(e)[:120]}")
                # LinkedIn rate-limit (429): stop hammering it this run
                if "429" in str(e):
                    break
                continue
            print(f"    -> {len(df)} results", flush=True)
            for _, r in df.iterrows():
                r = r.to_dict()
                url = _val(r, "job_url_direct") or _val(r, "job_url")
                jobs.append(Job(
                    company=_val(r, "company"),
                    title=_val(r, "title"),
                    url=url,
                    source={"linkedin": "LinkedIn", "naukri": "Naukri", "indeed": "Indeed"}.get(site, site),
                    location=_val(r, "location"),
                    description=_val(r, "description"),
                    posted_at=_val(r, "date_posted")[:10],
                    experience=_val(r, "experience_range"),
                    job_type_hint=_val(r, "job_type"),
                    extra={"listing_url": _val(r, "job_url")},
                ))
            time.sleep(2)
    if errors:
        ctx.setdefault("warnings", []).extend(errors)
        if not jobs:
            raise RuntimeError("; ".join(errors[:3]))
    return jobs
