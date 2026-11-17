"""Decides which jobs are fresher PM / growth roles and labels them."""
import re

from .models import Job

_YEARS_RE = re.compile(
    r"(\d{1,2})\s*(?:\+|-|–|—|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)",
    re.I,
)
_FRESHER_RE = re.compile(r"\bfreshers?\b|\b0\s*(?:-|–|to)\s*[12]\s*(?:years?|yrs?)|entry[- ]level|new grad", re.I)
_INTERN_RE = re.compile(r"\bintern(ship)?s?\b|\btrainee\b|\bapprentice", re.I)
_PPO_RE = re.compile(r"\bppo\b|pre[- ]placement offer", re.I)


def _norm(s: str) -> str:
    return " " + re.sub(r"[^a-z0-9&'’+.]+", " ", (s or "").lower()).strip() + " "


def _has_any(text: str, phrases) -> bool:
    t = _norm(text)
    return any(_norm(p) in t for p in phrases)


def categorize(title: str, cfg: dict) -> str:
    for cat, phrases in cfg["categories"].items():
        if _has_any(title, phrases):
            return cat
    return ""


def years_from_field(exp: str) -> int | None:
    """Experience fields like '3-8 Yrs', '0-1 years', '2+ years' (no context needed)."""
    m = re.search(r"(\d{1,2})\s*(?:\+|-|–|to)?\s*(\d{1,2})?\s*\+?\s*(?:years?|yrs?)", exp or "", re.I)
    return int(m.group(1)) if m else None


def min_years_required(text: str) -> int | None:
    """Smallest 'N years' requirement mentioned near experience wording."""
    if not text:
        return None
    best = None
    for m in _YEARS_RE.finditer(text):
        # look at a small window around the match for experience context
        window = text[max(0, m.start() - 60): m.end() + 40].lower()
        if not any(w in window for w in ("experience", "exp", "work", "industry", "relevant")):
            continue
        n = int(m.group(1))
        if n > 25:
            continue
        best = n if best is None else min(best, n)
    return best


def job_type(job: Job) -> str:
    trusted_hint = job.source in ("Internshala", "Lever", "Ashby", "Unstop") and _INTERN_RE.search(job.job_type_hint or "")
    is_intern = bool(_INTERN_RE.search(job.title or "")) or bool(trusted_hint)
    if is_intern and _PPO_RE.search(f"{job.title} {job.description}"):
        return "Intern + PPO"
    if is_intern:
        return "Intern"
    return "Full-time (Entry)"


def posted_date(text: str):
    """Best-effort posting date from ISO dates or phrases like '3 days ago'. None if unknown."""
    from datetime import date, datetime, timedelta
    if not text:
        return None
    t = str(text).strip().lower()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", t)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
        except ValueError:
            return None
    today = date.today()
    if any(w in t for w in ("just now", "today", "hour", "minute", "few")):
        return today
    if "yesterday" in t:
        return today - timedelta(days=1)
    m = re.search(r"(\d+|a|an)\+?\s*(day|week|month|year)s?\s*ago", t)
    if m:
        n = 1 if m.group(1) in ("a", "an") else int(m.group(1))
        days = {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)] * n
        return today - timedelta(days=days)
    return None


def location_ok(location: str, cfg: dict) -> bool:
    if not location or not location.strip():
        return True
    return _has_any(location, cfg["allowed_locations"])


def evaluate(job: Job, cfg: dict) -> tuple[bool, str]:
    """Returns (keep, reason). Fills job.category / job.job_type when kept."""
    title = job.title or ""
    if not title.strip():
        return False, "no title"
    if _has_any(title, cfg["exclude_titles"]):
        return False, "excluded title"
    if _has_any(title, cfg["exclude_seniority"]):
        return False, "senior"
    cat = categorize(title, cfg)
    if not cat:
        return False, "not a target role"
    if not location_ok(job.location, cfg):
        return False, "location"

    max_age = cfg.get("max_age_days")
    if max_age:
        from datetime import date
        d = posted_date(job.posted_at)
        if d is not None and (date.today() - d).days > max_age:
            return False, f"posted more than {max_age} days ago"

    jt = job_type(job)
    exp_text = f"{job.experience} {job.description}"
    yrs = years_from_field(job.experience)
    if yrs is None:
        yrs = min_years_required(job.description)
    if yrs is not None and yrs > cfg.get("max_min_years", 2):
        return False, f"needs {yrs}+ yrs"

    # A plain "Product Manager" full-time title is only kept if the JD
    # explicitly signals fresher / entry level.
    if jt == "Full-time (Entry)" and cat == "Product" and re.fullmatch(
        r"\s*(product manager)\s*", title.lower().split("-")[0].split("(")[0]
    ):
        if not _FRESHER_RE.search(exp_text) and not (yrs is not None and yrs <= 1):
            return False, "PM role without entry-level signal"

    job.category = cat
    job.job_type = jt
    if not job.experience and yrs is not None:
        job.experience = f"{yrs}+ yrs"
    return True, "ok"
