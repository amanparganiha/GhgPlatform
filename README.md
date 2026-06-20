# Carbon Emissions Reporting Platform (GHG Protocol · Scope 1 & 2)

A containerized prototype for tracking, calculating and visualizing an organization's
greenhouse-gas emissions under the **GHG Protocol**. It is built around **versioned
emission factors**, a **historically-accurate** calculation engine, and an analytics
layer that powers an ESG dashboard (year-over-year, intensity, and source hotspots).

> Built for the Exascale Deeptech & AI — Data Science Developer Intern assignment.
> Modelled on an integrated steel plant (inspired by the provided `GHG_Sheet_.xlsx`).

---

## TL;DR — run it

**Docker (recommended):**
```bash
docker build -t ghg-platform .
docker run -p 8000:8000 ghg-platform
# open http://localhost:8000
```

**Local (Python 3.11+):**
```bash
pip install -r requirements.txt
cd backend && uvicorn app:app --reload --port 8000
# open http://localhost:8000   (dashboard)   ·   http://localhost:8000/docs   (API)
```

The SQLite database is **created and seeded automatically on first start** — no manual
step. To reseed from scratch: `cd backend && python seed.py`.

---

## Architecture

```
                ┌──────────────────────────────────────────────────────────┐
   Browser ───► │  FastAPI (backend/app.py)                                 │
  (dashboard)   │                                                           │
                │   Core API ────────────┐      Analytics API ──────────┐   │
                │   POST /records         │      GET /analytics/yoy       │   │
                │   POST /records/{id}/   │      GET /analytics/intensity │   │
                │        override         │      GET /analytics/hotspot   │   │
                │   POST /metrics         │      GET /analytics/monthly   │   │
                │        │                │              │                │   │
                │        ▼                ▼              ▼                │   │
                │   calc.py  ◄── historical-accuracy ── analytics.py      │   │
                │        │   factor selection by date        │           │   │
                │        ▼                                    ▼           │   │
                │   ┌───────────────── SQLite (SQLAlchemy) ──────────────┐│   │
                │   │ emission_factors (versioned) · emission_records    ││   │
                │   │ audit_log · business_metrics                       ││   │
                │   └────────────────────────────────────────────────────┘│   │
                │   /  (static) ─► frontend/index.html  (Chart.js)         │   │
                └──────────────────────────────────────────────────────────┘
```

**Stack:** Python · FastAPI · SQLAlchemy 2.0 · SQLite · Chart.js · Docker.
One container, one port — the API and the dashboard share an origin.

---

## Data model (schema)

| Table | Purpose | Key columns |
|---|---|---|
| **emission_factors** | **Versioned** factors | `activity`, `scope`, `unit`, `co2e_per_unit`, `source`, `valid_from`, `valid_to` (null = current), `version` |
| **emission_records** | Each recorded emission | `scope`, `activity`, `factor_id` → factor used, `quantity`, `activity_date`, `calculated_emissions`, `final_emissions`, `is_overridden` |
| **audit_log** | Every create & override | `record_id`, `action`, `field`, `old_value`, `new_value`, `reason`, `user`, `created_at` |
| **business_metrics** | Metrics over time | `date`, `metric_name`, `value`, `unit` |

The schema is **scalable**: factors are decoupled from records, so adding a new yearly
factor is one row; records reference the factor that was actually applied.

---

## Calculation engine & historical accuracy

The core formula is:

```
Activity Data × Emission Factor = GHG Emissions (tCO₂e)
```

The important part is **which** factor: `calc.select_factor()` chooses the version whose
validity window **contains the activity's date** — not simply the latest one. So a January
2023 diesel entry is costed with the 2023 factor (2.65) even though a 2024 factor (2.68)
now exists. This is what makes restating prior years correct.

**Manual overrides** go through `calc.override_record()`, which updates `final_emissions`,
flags the record, and writes a full **audit-log** entry (old value → new value, reason,
user, timestamp). Analytics always read `final_emissions`, so overrides flow through.

---

## Seeded sample data

`seed.py` populates a demo-ready dataset for a ~11 MtCO₂e/year integrated steel plant:
- **Emission factors** — 10 sources, each with a **2023 (now expired)** and **2024
  (current)** version; two sources also carry a 2022 version, so multiple versions and
  "expired factors for past years" are present.
- **Emission records** — monthly records for **all of 2023 and 2024**, each created through
  the engine so it picks the date-valid factor.
- **Business metrics** — monthly tonnes of steel + yearly headcount (drives intensity).

---

## API

**Core (create / override):**
| Method & path | Purpose |
|---|---|
| `POST /records` | Create a Scope 1 or 2 emission record (auto-selects the date-valid factor, computes tCO₂e) |
| `POST /records/{id}/override` | Manually override emissions, with audit trail |
| `POST /metrics` | Add a business metric |
| `GET /records` · `GET /factors` · `GET /audit` · `GET /metrics` | Read endpoints |

**Analytics (the high-value milestone):**
| Path | Returns |
|---|---|
| `GET /analytics/yoy` | Total emissions by scope, current vs previous year |
| `GET /analytics/intensity?year=` | kgCO₂e per tonne of product (and per employee) |
| `GET /analytics/hotspot?year=` | Emissions by source, largest contributors first |
| `GET /analytics/monthly?year=` | Monthly emissions (split by scope) for the trend line |

`GET /docs` gives interactive Swagger UI.

---

## Dashboard

`frontend/index.html` (Chart.js) — an ESG annual-report style dashboard with all four
mandatory visualizations plus the data-entry forms:
1. **Stacked bar** — YoY emissions, Scope 1 vs Scope 2.
2. **Donut** — emission hotspots by source.
3. **KPI cards** — the headline **emission intensity** (kgCO₂e / tonne) + totals.
4. **Line chart** — monthly emissions trend, split by scope.
- **Forms** to submit a Scope 1/2 record and a business metric.
- A **versioned-factor table** that visibly shows current vs expired factors.

It calls the API on the same origin and falls back to bundled sample data if the API is
unreachable, so it always renders.

---

## Project structure

```
ghg_platform/
├── Dockerfile · .dockerignore · requirements.txt · README.md
├── data/
│   └── GHG_Sheet_.xlsx          # provided source data (bundled)
├── backend/
│   ├── database.py              # SQLAlchemy models (4 tables)
│   ├── calc.py                  # calc engine + historical accuracy + override/audit
│   ├── analytics.py             # YoY · intensity · hotspot · monthly
│   ├── seed.py                  # versioned factors + 2 years of records + metrics
│   └── app.py                   # FastAPI routes + static mount
└── frontend/
    └── index.html               # dashboard (4 charts + forms + factor table)
```

---

## Deploying a public link

One container, so any container host works:
- **Render.com** → New Web Service → Deploy from a Dockerfile.
- **Hugging Face Spaces** (Docker SDK) → set app port 8000.
- **Railway / Fly.io** → `Dockerfile` auto-detected.

SQLite lives inside the container; for a multi-instance production deployment you would
point SQLAlchemy at Postgres (one line in `database.py`).

---

## Notes & next steps

- **Scope 3** is out of scope per the brief (focus on Scope 1 & 2); the schema already
  accommodates it via the `scope` column.
- Figures are illustrative (scaled to a believable plant size) but the structure mirrors
  the provided sheet — sources, sections and the factor logic are real.
- Next: role-based auth on overrides, Postgres for multi-user, and an emissions-target /
  reduction-pathway view.
