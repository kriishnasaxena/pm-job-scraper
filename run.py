"""Entry point.

  python run.py --group fast          # APIs, LinkedIn/Naukri/Indeed, Internshala, YC
  python run.py --group browser       # browser-based sources (phase 4)
  python run.py --group all
  python run.py --dry-run             # no Google creds needed; writes ./out/*.csv
  python run.py --only internshala    # run a single source
"""
import argparse
import importlib
import os
import sys
import time
import traceback
from collections import Counter
from datetime import datetime

import yaml

from core.dedupe import dup_key, job_id
from core.filters import evaluate
from core.models import IST

SOURCE_MODULES = {
    "ats_apis": "sources.ats_apis",
    "jobspy": "sources.jobspy_boards",
    "internshala": "sources.internshala",
    "yc": "sources.yc",
    "unstop": "sources.unstop",
    "instahyre": "sources.instahyre",
    "cutshort": "sources.cutshort",
    "wellfound": "sources.wellfound",
}


def title_prefilter(job, cfg):
    """Cheap check before fetching detail pages: title/seniority/category only."""
    from core.filters import categorize, _has_any
    t = job.title or ""
    return bool(t.strip()) and not _has_any(t, cfg["exclude_titles"]) \
        and not _has_any(t, cfg["exclude_seniority"]) and bool(categorize(t, cfg))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="fast", choices=["fast", "browser", "all"])
    ap.add_argument("--only", help="run just one source by name")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--prune", action="store_true",
                    help="re-check rows still marked New against the current filters and delete failures")
    ap.add_argument("--backfill", action="store_true",
                    help="look back max_age_days on LinkedIn/Naukri/Indeed instead of a few hours")
    ap.add_argument("--config", default="config.yaml")
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.dry_run:
        from core.sheet import LocalStore
        store = LocalStore()
    else:
        from core.sheet import SheetStore
        sheet_id = os.environ.get("SHEET_ID")
        creds = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sheet_id or not creds:
            sys.exit("Missing SHEET_ID or GOOGLE_SERVICE_ACCOUNT_JSON (or use --dry-run).")
        store = SheetStore(sheet_id, creds)

    if args.prune and hasattr(store, "prune"):
        from core.models import Job

        def _keep(row):
            j = Job(company=row.get("Company", ""), title=row.get("Role", ""), url=row.get("Apply link", ""),
                    source=row.get("Source", ""), location=row.get("Location", ""),
                    description=row.get("Full JD", ""), posted_at=row.get("Posted on", ""),
                    experience=row.get("Exp", ""))
            if not j.experience:   # Naukri URLs carry experience: ...-3-to-8-years-...
                import re
                m = re.search(r"-(\d{1,2})-to-(\d{1,2})-years", j.url)
                if m:
                    j.experience = f"{m.group(1)}-{m.group(2)} Yrs"
            return title_prefilter(j, cfg) and evaluate(j, cfg)[0]
        print(f"Pruned {store.prune(_keep)} rows that no longer pass the filters.", flush=True)

    seen_ids, seen_dups = store.seen()
    run_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M")
    total_new = 0

    for name, mod_path in SOURCE_MODULES.items():
        sc = cfg["sources"].get(name, {})
        if args.only and name != args.only:
            continue
        if not args.only and (not sc.get("enabled") or (args.group != "all" and sc.get("group") != args.group)):
            continue

        mod = importlib.import_module(mod_path)
        ctx = {"store": store, "backfill": args.backfill}
        t0 = time.time()
        fetched = kept = new = 0
        rows = []
        err = ""
        print(f"[{name}] starting…", flush=True)
        try:
            jobs = mod.fetch(cfg, ctx)
            fetched = len(jobs)

            # 1) title-level filter + dedupe BEFORE any detail-page requests
            candidates = []
            for j in jobs:
                if not j.url or not title_prefilter(j, cfg):
                    continue
                jid, dk = job_id(j.url), dup_key(j.company, j.title)
                if jid in seen_ids or dk in seen_dups:
                    continue
                seen_ids.add(jid); seen_dups.add(dk)   # also dedupes within this run
                candidates.append((j, jid, dk))

            # 2) fetch JDs for sources that need it (bounded per run)
            if hasattr(mod, "enrich"):
                limit = sc.get("max_detail_pages", 20)
                for j, _, _ in candidates[:limit]:
                    try:
                        mod.enrich(j, cfg)
                    except Exception as e:
                        ctx.setdefault("warnings", []).append(f"detail {j.url}: {e}")
                candidates = candidates[:limit]

            # 3) full filter (experience, location, entry-level checks)
            per_company = Counter()
            for j, jid, dk in candidates:
                ok, _reason = evaluate(j, cfg)
                if ok:
                    rows.append(j.to_row(jid, dk))
                    per_company[j.company] += 1
                    new += 1
            kept = new

            if name == "ats_apis" and ctx.get("company_updates"):
                comp_by_row = {c["row"]: c["company"] for c in store.read_companies()}
                for u in ctx["company_updates"]:
                    if u["ats"] != "not-found":
                        u["matching"] = per_company.get(comp_by_row.get(u["row"], ""), 0)
                store.update_companies(ctx["company_updates"])
        except Exception as e:
            err = f"{e.__class__.__name__}: {str(e)[:300]}"
            traceback.print_exc()

        warn = "; ".join(ctx.get("warnings", [])[:5])
        msg = err or (f"warnings: {warn}"[:500] if warn else "")
        # Save straight away, so a slow source later on can't lose this work
        try:
            store.add_jobs(rows)
            store.log_health([[run_at, name, fetched, kept, new, msg]])
        except Exception as e:
            print(f"[{name}] couldn't write to sheet: {e}", flush=True)
        total_new += new
        print(f"[{name}] fetched={fetched} new={new} {('ERR ' + err) if err else ''} "
              f"({time.time() - t0:.0f}s)", flush=True)

    print(f"Done. {total_new} new jobs added.", flush=True)


if __name__ == "__main__":
    main()
