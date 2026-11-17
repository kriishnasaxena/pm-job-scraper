import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from core.dedupe import dup_key, job_id, normalize_url  # noqa: E402
from core.filters import evaluate, min_years_required  # noqa: E402
from core.models import Job  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(__file__), "..", "config.yaml")))


def J(title, loc="Bengaluru", desc="", **kw):
    return Job(company="Acme", title=title, url="https://x.com/1", source="t", location=loc, description=desc, **kw)


def keep(job):
    return evaluate(job, CFG)[0]


def test_keeps_target_roles():
    for t in ["Product Intern", "Associate Product Manager", "APM - Payments", "Product Analyst",
              "Growth Intern", "Growth Marketing Associate", "Founder's Office Intern",
              "Business Analyst Intern", "Product Management Intern (6 months)"]:
        assert keep(J(t)), t


def test_drops_senior_and_sales():
    for t in ["Senior Product Manager", "Lead Product Analyst", "Group Product Manager",
              "Director, Growth", "Inside Sales Executive - Growth", "Software Engineer Intern",
              "Business Development Executive"]:
        assert not keep(J(t)), t


def test_experience_filter():
    assert not keep(J("Product Analyst", desc="We need 3-5 years of experience in analytics"))
    assert keep(J("Product Analyst", desc="0-2 years of experience preferred"))
    assert keep(J("Product Analyst", desc="Founded 10 years ago. Freshers welcome"))
    assert min_years_required("Minimum 4+ yrs of relevant experience") == 4


def test_plain_pm_needs_entry_signal():
    assert not keep(J("Product Manager", desc="Own the roadmap."))
    assert keep(J("Product Manager", desc="Entry-level role, freshers welcome."))


def test_location():
    assert keep(J("Product Intern", loc="Remote"))
    assert keep(J("Product Intern", loc=""))
    assert not keep(J("Product Intern", loc="San Francisco, CA"))


def test_types():
    j = J("Product Intern", desc="Stipend + PPO for top performers"); keep(j)
    assert j.job_type == "Intern + PPO" and j.category == "Product"
    j = J("Growth Analyst", desc="0-1 years"); keep(j)
    assert j.job_type == "Full-time (Entry)" and j.category == "Growth"


def test_dedupe():
    a = "https://www.linkedin.com/jobs/view/product-intern-at-acme-4012345678?trk=abc&refId=x"
    b = "https://in.linkedin.com/jobs/view/4012345678/"
    assert normalize_url(a) == normalize_url(b)
    assert job_id("https://jobs.lever.co/acme/123?lever-source=x") == job_id("https://jobs.lever.co/acme/123/")
    assert dup_key("Acme Technologies Pvt Ltd", "Product Intern") == dup_key("ACME", "Product  Intern")


def test_internshala_parsing(monkeypatch, tmp_path):
    import core.scrape as scrape
    from scrapling.parser import Selector
    import sources.internshala as ish

    html = """<div class='container'>
      <div class='individual_internship' internshipid='1' data-href='/internship/detail/product-management-internship-in-bangalore-at-acme-labs1712345'>
        <h3 class='job-internship-name'><a href='/internship/detail/product-management-internship-in-bangalore-at-acme-labs1712345'>Product Management</a></h3>
        <p class='company-name'>Acme Labs</p><div class='locations'><a>Bangalore</a></div></div>
      <div class='individual_internship' internshipid='2' data-href='/internship/detail/growth-intern-at-foo1712346'>
        <h3 class='job-internship-name'><a>Growth Intern</a></h3>
        <p class='company-name'>Foo</p><div class='locations'><a>Work from home</a></div></div></div>"""
    db = str(tmp_path / "a.db")

    def fake_get(url, delay=0):
        return Selector(html, url="https://internshala.com/x", adaptive=True,
                        storage_args={"storage_file": db, "url": "https://internshala.com/x"})
    monkeypatch.setattr(ish, "get_page", fake_get)
    cfg = dict(CFG); cfg["sources"] = {"internshala": {"urls": ["https://internshala.com/internships/x/"]}}
    jobs = ish.fetch(cfg, {})
    assert [(j.title, j.company, j.location) for j in jobs] == [
        ("Product Management", "Acme Labs", "Bangalore"), ("Growth Intern", "Foo", "Work from home")]
    assert jobs[0].url.startswith("https://internshala.com/internship/detail/")

    # Site renames its classes -> adaptive selectors still find the cards
    renamed = html.replace("individual_internship", "intern-card-v2")
    monkeypatch.setattr(ish, "get_page", lambda u, d=0: Selector(
        renamed, url="https://internshala.com/x", adaptive=True,
        storage_args={"storage_file": db, "url": "https://internshala.com/x"}))
    jobs2 = ish.fetch(cfg, {})
    assert len(jobs2) == 2


def test_ats_parsers(monkeypatch):
    import sources.ats_apis as ats
    gh = {"jobs": [{"title": "Product Intern", "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                    "location": {"name": "Bengaluru"}, "content": "&lt;p&gt;Hi&lt;/p&gt;", "updated_at": __import__("datetime").date.today().isoformat() + "T00:00:00Z"}]}
    lever = [{"text": "Growth Analyst", "applyUrl": "https://jobs.lever.co/foo/2/apply",
              "categories": {"location": "Mumbai", "commitment": "Full-time"},
              "descriptionPlain": "0-1 years", "lists": [], "createdAt": int(__import__("time").time() * 1000)}]

    def fake_get(url):
        if "greenhouse" in url and "/acme/" in url:
            return gh
        if "lever" in url and "/foo" in url:
            return lever
        return None
    monkeypatch.setattr(ats, "_get", fake_get)

    class Store:
        def read_companies(self):
            return [{"row": 2, "company": "Acme", "slug": "acme", "ats": "auto"},
                    {"row": 3, "company": "Foo", "slug": "foo", "ats": "auto"},
                    {"row": 4, "company": "Nope", "slug": "nope", "ats": "auto"}]
    ctx = {"store": Store()}
    jobs = ats.fetch(CFG, ctx)
    assert {j.source for j in jobs} == {"Greenhouse", "Lever"}
    ups = {u["row"]: u["ats"] for u in ctx["company_updates"]}
    assert ups == {2: "greenhouse", 3: "lever", 4: "not-found"}
    assert keep(jobs[0]) and keep(jobs[1])


def test_row_shape():
    from core.models import COLUMNS
    j = J("Product Intern", desc="<p>Hello</p>"); keep(j)
    row = j.to_row("id1", "dk")
    assert len(row) == len(COLUMNS) and row[COLUMNS.index("Status")] == "New"
    assert row[COLUMNS.index("Full JD")] == "Hello"


def test_max_age():
    from datetime import date, timedelta
    old = (date.today() - timedelta(days=12)).isoformat()
    new = (date.today() - timedelta(days=3)).isoformat()
    assert not keep(J("Product Intern", posted_at=old))
    assert keep(J("Product Intern", posted_at=new))
    assert keep(J("Product Intern", posted_at=""))              # unknown date kept
    assert not keep(J("Product Intern", posted_at="Posted 2 weeks ago"))
    assert keep(J("Product Intern", posted_at="Posted 4 days ago"))
    assert keep(J("Product Intern", posted_at="Few hours ago"))


def test_naukri_style_experience_and_type():
    j = J("Product Manager (PM + Scrum Master)", experience="7-11 Yrs", job_type_hint="internship")
    j.source = "Naukri"
    assert not keep(j)
    j = J("Business Analyst", experience="3-8 Yrs"); j.source = "Naukri"
    assert not keep(j)
    j = J("Product Intern - Algo Trading", experience="0-2 Yrs"); j.source = "Naukri"
    assert keep(j) and j.job_type == "Intern"
    j = J("Product Management"); j.source = "Internshala"; j.job_type_hint = "internship"
    assert keep(j) and j.job_type == "Intern"
