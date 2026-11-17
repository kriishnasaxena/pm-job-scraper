"""Temporary: load job pages in a real browser on GitHub's runner and record
the rendered HTML plus every JSON API response, so scrapers can be written
against real page structure."""
import json, os, re, sys
from playwright.sync_api import sync_playwright

URLS = {
    "instahyre_search": "https://www.instahyre.com/search-jobs/?designation=Product%20Manager",
    "instahyre_seo": "https://www.instahyre.com/product-manager-jobs/",
    "cutshort_pm": "https://cutshort.io/jobs/product-manager-jobs",
    "cutshort_pmgmt": "https://cutshort.io/jobs/product-management-jobs",
    "unstop_intern": "https://unstop.com/internships?search=product",
    "unstop_jobs": "https://unstop.com/jobs?search=product%20manager",
    "wellfound_india": "https://wellfound.com/role/l/product-manager/india",
    "wellfound_remote": "https://wellfound.com/role/r/product-manager",
}
os.makedirs("probe_out", exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(headless=True)
    ctx = b.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36", locale="en-IN")
    for name, url in URLS.items():
        page = ctx.new_page()
        calls = []
        def on_resp(r, calls=calls):
            try:
                ct = r.headers.get("content-type", "")
                if "json" in ct and r.request.resource_type in ("xhr", "fetch"):
                    calls.append({"url": r.url, "status": r.status, "body": r.text()[:30000]})
            except Exception as e:
                calls.append({"url": r.url, "err": str(e)})
        page.on("response", on_resp)
        status = None
        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
            status = resp.status if resp else None
            page.wait_for_timeout(8000)
            page.mouse.wheel(0, 4000); page.wait_for_timeout(3000)
        except Exception as e:
            print(name, "ERR", e)
        html = page.content()
        open(f"probe_out/{name}.html", "w").write(html[:3_000_000])
        json.dump({"url": url, "status": status, "final_url": page.url, "title": page.title(),
                   "calls": calls}, open(f"probe_out/{name}.json", "w"), indent=1)
        print(f"{name}: status={status} html={len(html)} json_calls={len(calls)} title={page.title()[:60]!r}")
        page.close()
    b.close()
