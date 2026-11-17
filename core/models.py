from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

# Order of columns in the "Jobs" tab. Keep in sync with sheet.py.
COLUMNS = [
    "Found at", "Posted on", "Company", "Role", "Category", "Type",
    "Location", "Exp", "Source", "Apply link", "JD summary", "Full JD",
    "Status", "Notes", "ID", "Dup key",
]

SHEET_CELL_LIMIT = 45_000  # Google Sheets hard limit is 50,000 chars per cell


@dataclass
class Job:
    company: str
    title: str
    url: str                      # apply link (or posting link)
    source: str
    location: str = ""
    description: str = ""
    posted_at: str = ""           # free text / ISO date, as the source gives it
    experience: str = ""          # e.g. "0-2 yrs" if the source exposes it
    job_type_hint: str = ""       # e.g. "internship", "fulltime" from the source
    category: str = ""            # filled by filters
    job_type: str = ""            # filled by filters
    extra: dict = field(default_factory=dict)   # source-specific (e.g. detail url)

    def to_row(self, job_id: str, dup_key: str) -> list:
        jd = clean_text(self.description)
        summary = jd[:400] + ("…" if len(jd) > 400 else "")
        return [
            datetime.now(IST).strftime("%Y-%m-%d %H:%M"),
            self.posted_at,
            self.company,
            self.title,
            self.category,
            self.job_type,
            self.location,
            self.experience,
            self.source,
            self.url,
            summary,
            jd[:SHEET_CELL_LIMIT],
            "New",
            "",
            job_id,
            dup_key,
        ]


def clean_text(s: str) -> str:
    import html
    import re
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)          # strip any leftover HTML tags
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n\s*\n+", "\n", s)
    return s.strip()
