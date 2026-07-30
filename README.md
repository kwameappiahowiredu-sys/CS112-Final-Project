# CS 112 Final Course Project — Week 1 Package

**National Electricity Grid Network Analysis · GridCare-Lite · ClinicCare-Lite**

This is a working Week 1 foundation for all three project components: the data-science grid analysis, the GridCare-Lite desktop app, and the ClinicCare-Lite web app. Everything under `data-science/`, `gridcare-lite/`, and `cliniccare-lite/` has actually been run and verified in this environment (see each folder's smoke test) — this isn't just scaffolding that looks right, it's confirmed to work.

## Structure

```
cs112-project/
├── data-science/
│   ├── generate_dataset.py       # seeded generator -- verified: 10 utilities, 44 substations, 55 lines
│   ├── utilities.csv / substations.csv / lines.csv
│   ├── 01_load_inspect.py        # Task 1: load + inspect
│   ├── 02_clean_validate.py      # Task 2 / 1.1: cleaning + validation + FK checks
│   ├── validation_output.txt     # raw output from the validation run
│   └── data_cleaning_report.md   # findings, incl. one genuine data-quality issue found
├── gridcare-lite/
│   ├── db.py                     # SQLite schema + CSV import from data-science/
│   ├── main.py                   # Tkinter login + outage dashboard
│   └── smoke_test.py             # headless DB round-trip test (passes)
├── cliniccare-lite/
│   ├── app.py                    # Flask app: login, dashboard, logout
│   ├── models/                   # User, HealthTask, TaskSubmission
│   ├── utils/email_handler.py    # SMTP notifications (env-var credentials)
│   ├── templates/                # login, clinician + patient dashboards
│   ├── data/                     # users.json etc. (empty stubs, ready to populate)
│   └── smoke_test.py             # model + Flask test-client checks (passes)
└── docs/
    ├── week1-checklist.md
    ├── coding-standards.md
    ├── test-plan-template.md
    ├── cliniccare-ethical-boundary.md
    ├── erd-gridcare-lite.mermaid
    └── erd-cliniccare-lite.mermaid
```

## Running it yourself

```bash
# Data science
cd data-science && python3 generate_dataset.py && python3 01_load_inspect.py && python3 02_clean_validate.py

# GridCare-Lite (needs a display for the actual window; DB logic runs headless)
cd gridcare-lite && python3 smoke_test.py     # headless check
cd gridcare-lite && python3 main.py           # opens the actual Tkinter window

# ClinicCare-Lite
cd cliniccare-lite && pip install flask bcrypt --break-system-packages
python3 smoke_test.py                          # headless check
python3 app.py                                 # starts the Flask dev server on :5000
```

## What's a team decision, not a technical one

This package makes reasonable Week 1 defaults so there's something concrete to react to, but a few things are genuinely your team's call, not something code can decide:
- **Role split** across grid analysis / GridCare-Lite / ClinicCare-Lite / visualization / testing — the brief explicitly allows deviating from its suggested 4-person templates (e.g. one member per app, or a 3+1 data-heavy split).
- **GridCare-Lite framework** — built here with Tkinter (the brief's first-listed option); swap to PyQt if your team prefers it.
- **Repository layout** — this folder structure is ready to drop straight into the shared GitHub repo as-is, but confirm it matches whatever's already there.

See `docs/week1-checklist.md` for the full task-by-task status against the brief's Week 1 requirements.
