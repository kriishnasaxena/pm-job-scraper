"""IDs used to recognise a job we've already put in the sheet."""
import hashlib
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# Query params that change between visits but don't change the job
_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
             "ref", "refid", "trk", "trackingid", "src", "source", "gh_src", "lever-source"}


def normalize_url(url: str) -> str:
    if not url:
        return ""
    p = urlsplit(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in _TRACKING]
    path = p.path.rstrip("/")
    # LinkedIn: keep only the numeric job id
    m = re.search(r"linkedin\.com/jobs/view/(?:[^/]*?-)?(\d+)", url)
    if m:
        return f"linkedin:{m.group(1)}"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, urlencode(q), ""))


def job_id(url: str) -> str:
    return hashlib.sha1(normalize_url(url).encode()).hexdigest()[:16]


def dup_key(company: str, title: str) -> str:
    """Catches the same role posted on several sites (e.g. LinkedIn + Naukri)."""
    def n(s):
        s = (s or "").lower()
        s = re.sub(r"\b(pvt|private|ltd|limited|inc|llp|technologies|technology|labs|india)\b", " ", s)
        return re.sub(r"[^a-z0-9]+", "", s)
    return f"{n(company)}|{n(title)}"
