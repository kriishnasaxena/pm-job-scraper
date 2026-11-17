"""Reads from / writes to the Google Sheet. Never edits rows that already exist."""
import csv
import json
import os
from datetime import datetime

from .models import COLUMNS, IST

STATUS_COL = COLUMNS.index("Status")          # 0-based
ID_COL = COLUMNS.index("ID") + 1             # 1-based for gspread
DUP_COL = COLUMNS.index("Dup key") + 1
STATUSES = ["New", "Applied", "Interviewing", "Rejected", "Skip"]

COMPANY_HEADERS = ["Company", "Slug", "ATS", "Status", "Last checked", "Matching jobs"]
HEALTH_HEADERS = ["Run at", "Source", "Fetched", "Kept", "New", "Error"]


class SheetStore:
    def __init__(self, sheet_id: str, creds_json: str):
        import gspread
        info = json.loads(creds_json)
        gc = gspread.service_account_from_dict(info)
        sheet_id = sheet_id.strip()
        if "/d/" in sheet_id:          # full URL pasted instead of just the ID
            sheet_id = sheet_id.split("/d/")[1].split("/")[0]
        try:
            self.sh = gc.open_by_key(sheet_id)
        except Exception as e:
            raise SystemExit(
                f"\nCan't open the Google Sheet (ID {sheet_id[:6]}…).\n"
                f"Share the sheet with {info.get('client_email')} as Editor.\n"
                "If you can't share it outside your college account, make a copy from your "
                "personal Gmail, share that copy instead, and update the SHEET_ID secret.\n"
                f"(Google said: {str(e)[:120]})") from None
        self.jobs = self._tab("Jobs", COLUMNS)
        self.companies = self._tab("Companies", COMPANY_HEADERS)
        self.health = self._tab("Health", HEALTH_HEADERS)

    def _tab(self, name, headers):
        import gspread
        try:
            ws = self.sh.worksheet(name)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(name, rows=1000, cols=len(headers))
        if ws.row_values(1)[: len(headers)] != headers:
            ws.update(values=[headers], range_name="A1")
        return ws

    # ---------- jobs ----------
    def seen(self) -> tuple[set, set]:
        ids = set(v for v in self.jobs.col_values(ID_COL)[1:] if v)
        dups = set(v for v in self.jobs.col_values(DUP_COL)[1:] if v)
        return ids, dups

    def add_jobs(self, rows: list[list]):
        if not rows:
            return
        # newest on top; existing rows (and your Status/Notes) just move down
        self.jobs.insert_rows(rows, row=2, value_input_option="RAW")
        self.sh.batch_update({"requests": [{
            "setDataValidation": {
                "range": {"sheetId": self.jobs.id, "startRowIndex": 1,
                          "endRowIndex": self.jobs.row_count,
                          "startColumnIndex": STATUS_COL, "endColumnIndex": STATUS_COL + 1},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                                       "values": [{"userEnteredValue": s} for s in STATUSES]},
                         "strict": False, "showCustomUi": True},
            }}]})

    # ---------- companies ----------
    def read_companies(self) -> list[dict]:
        out = []
        for i, r in enumerate(self.companies.get_all_values()[1:], start=2):
            r = (r + [""] * 6)[:6]
            if not r[0].strip():
                continue
            out.append({"row": i, "company": r[0].strip(), "slug": r[1].strip() or r[0].strip().lower().replace(" ", ""),
                        "ats": (r[2].strip() or "auto").lower()})
        return out

    def update_companies(self, updates: list[dict]):
        """updates: [{row, ats, status, matching}] -> writes C:F for each row in one call."""
        if not updates:
            return
        now = datetime.now(IST).strftime("%Y-%m-%d %H:%M")
        data = [{"range": f"C{u['row']}:F{u['row']}",
                 "values": [[u["ats"], u["status"], now, u.get("matching", "")]]} for u in updates]
        self.companies.batch_update(data, value_input_option="RAW")

    # ---------- health ----------
    def log_health(self, rows: list[list]):
        if rows:
            self.health.insert_rows(rows, row=2, value_input_option="RAW")


class LocalStore:
    """Used with --dry-run: no Google credentials needed, writes CSVs in ./out/."""

    def __init__(self, out_dir="out", companies_csv="companies_seed.csv"):
        os.makedirs(out_dir, exist_ok=True)
        self.out_dir = out_dir
        self.companies_csv = companies_csv
        self.jobs_csv = os.path.join(out_dir, "jobs.csv")

    def seen(self):
        ids, dups = set(), set()
        if os.path.exists(self.jobs_csv):
            with open(self.jobs_csv, newline="", encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    ids.add(r["ID"]); dups.add(r["Dup key"])
        return ids, dups

    def add_jobs(self, rows):
        new_file = not os.path.exists(self.jobs_csv)
        with open(self.jobs_csv, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(COLUMNS)
            w.writerows(rows)

    def read_companies(self):
        out = []
        if not os.path.exists(self.companies_csv):
            return out
        with open(self.companies_csv, newline="", encoding="utf-8") as f:
            for i, r in enumerate(csv.DictReader(f), start=2):
                out.append({"row": i, "company": r["Company"], "slug": r["Slug"], "ats": (r.get("ATS") or "auto").lower()})
        return out

    def update_companies(self, updates):
        with open(os.path.join(self.out_dir, "company_updates.json"), "w") as f:
            json.dump(updates, f, indent=1)

    def log_health(self, rows):
        with open(os.path.join(self.out_dir, "health.csv"), "a", newline="") as f:
            csv.writer(f).writerows(rows)
