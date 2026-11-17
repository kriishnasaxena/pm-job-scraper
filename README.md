# PM Job Scraper

Every hour this collects fresher **Product, Growth and Founder's Office / Strategy** roles in India
from company career pages, LinkedIn, Naukri, Indeed, Internshala and YC startups. It filters
out senior and sales roles, skips duplicates, and adds new jobs (with JD + apply link)
to the top of a Google Sheet. Rows you've already edited are never changed.

| Source | How | 
|---|---|
| ~100 company career pages (Greenhouse / Lever / Ashby) | Public JSON APIs |
| LinkedIn, Naukri, Indeed | [JobSpy](https://github.com/speedyapply/JobSpy), no login |
| Internshala, YC Startups | [Scrapling](https://github.com/D4Vinci/Scrapling) with adaptive selectors |

---

## One-time setup (about 15 minutes)

### 1. Google Cloud service account (the bot that writes to your sheet)
1. Go to <https://console.cloud.google.com/> → create a project called `pm-job-scraper`.
2. **APIs & Services → Library** → enable **Google Sheets API** and **Google Drive API**.
3. **APIs & Services → Credentials → Create credentials → Service account**. Name it `scraper`, click **Done** (skip the optional steps).
4. Open the new service account → **Keys → Add key → Create new key → JSON**. A `.json` file downloads.
   **Keep it private**. Never commit it to GitHub.
5. Copy the service account's email (looks like `scraper@pm-job-scraper.iam.gserviceaccount.com`).

### 2. Share the Google Sheet with that email
Open your sheet → **Share** → paste the service-account email → **Editor** → Send.

> If you get "can't share outside your organisation" (common with college accounts), open the
> sheet → **File → Make a copy** while logged into your personal Gmail, and use the copy.

The **Sheet ID** is the long part of the sheet URL:
`docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`

### 3. Put the code on GitHub
Create a new **public** repo called `pm-job-scraper` (no README), then from this folder:
```bash
git init
git add .
git commit -m "PM job scraper v1"
git branch -M main
git remote add origin https://github.com/kriishnasaxena/pm-job-scraper.git
git push -u origin main
```

### 4. Add the two secrets
Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `SHEET_ID` | the Sheet ID from step 2 |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | open the downloaded `.json` file in a text editor and paste **all** of it |

### 5. First run
Repo → **Actions** → enable workflows if asked → **Scrape jobs** → **Run workflow**.
After 3–6 minutes jobs appear in the **Jobs** tab, and the **Health** tab shows how each source did.
From then on it runs by itself every hour.

---

## Day-to-day
- **Jobs tab:** change **Status** (New / Applied / Interviewing / Rejected / Skip) and add **Notes**. Filter by Category or Type.
- **Companies tab:** add any company: name + slug (the bit in its careers URL, e.g. `jobs.lever.co/`**`acme`**), ATS = `auto`.
  The first run detects whether it's on Greenhouse, Lever or Ashby. `not-found` means it uses a
  different system (Keka, Darwinbox, Zoho…), which this can't read yet. Fix the slug or delete the row.
- **Health tab:** if a source shows 0 fetched or an error for several runs, the site changed or blocked us.
- **Change what's scraped:** edit `config.yaml` on GitHub (keywords, excluded titles, cities, search terms).

## Good to know
- GitHub's hourly schedule can run 5–20 minutes late, and gets paused if the repo has **no activity for 60 days**.
  If that happens, Actions shows a banner; click **Enable workflow**.
- LinkedIn sometimes rate-limits GitHub's servers. That shows up in Health as a 429 error and usually clears by the next run.
- LinkedIn's terms don't allow automated scraping. This uses no login and keeps volume low, but be aware.

## Run locally (optional)
```bash
pip install -r requirements.txt
python run.py --dry-run           # no Google needed; writes out/jobs.csv
python run.py --dry-run --only internshala
python -m pytest -q tests
```

## Roadmap
- Phase 4: Instahyre, Cutshort, Unstop (Scrapling DynamicFetcher), Wellfound (StealthyFetcher)
- v2: Telegram alert on new jobs; optional Streamlit dashboard
- v3: LinkedIn job-alert emails via Gmail; fit score vs resume
