"""
Analytics & reporting engine — powers the dashboard and the high-value APIs.

  - yoy          : total emissions by scope, current vs previous year
  - intensity    : kgCO2e per tonne of product (and per employee) for a period
  - hotspot      : emissions broken down by source, largest contributors first
  - monthly_trend: monthly total emissions for a year (split by scope)

All figures use each record's `final_emissions` (so manual overrides are respected)
and emissions are stored in tCO2e; intensity is reported in kgCO2e per unit.
"""
from __future__ import annotations
from sqlalchemy import func, extract, select
from sqlalchemy.orm import Session
from database import EmissionRecord, BusinessMetric

T_TO_KG = 1000.0


def available_years(db: Session) -> list[int]:
    yrs = db.execute(select(func.distinct(extract("year", EmissionRecord.activity_date)))).scalars().all()
    return sorted(int(y) for y in yrs)


def _scope_totals(db: Session, year: int) -> dict:
    rows = (db.query(EmissionRecord.scope, func.sum(EmissionRecord.final_emissions))
            .filter(extract("year", EmissionRecord.activity_date) == year)
            .group_by(EmissionRecord.scope).all())
    d = {f"scope{int(s)}": round(v, 2) for s, v in rows}
    d.setdefault("scope1", 0.0); d.setdefault("scope2", 0.0)
    d["total"] = round(d["scope1"] + d["scope2"], 2)
    return d


def yoy(db: Session) -> dict:
    yrs = available_years(db)
    cur = yrs[-1]; prev = yrs[-2] if len(yrs) > 1 else yrs[-1]
    cur_t, prev_t = _scope_totals(db, cur), _scope_totals(db, prev)
    change = (round((cur_t["total"] - prev_t["total"]) / prev_t["total"] * 100, 1)
              if prev_t["total"] else None)
    return {"unit": "tCO2e", "current_year": cur, "previous_year": prev,
            "current": cur_t, "previous": prev_t, "total_change_pct": change}


def _steel_tonnes(db: Session, year: int) -> float:
    v = (db.query(func.sum(BusinessMetric.value))
         .filter(BusinessMetric.metric_name == "Tonnes of Steel Produced",
                 extract("year", BusinessMetric.date) == year).scalar())
    return float(v or 0)


def _employees(db: Session, year: int) -> float:
    v = (db.query(BusinessMetric.value)
         .filter(BusinessMetric.metric_name == "Number of Employees",
                 extract("year", BusinessMetric.date) == year)
         .order_by(BusinessMetric.date.desc()).first())
    return float(v[0]) if v else 0.0


def intensity(db: Session, year: int) -> dict:
    totals = _scope_totals(db, year)
    emissions_kg = totals["total"] * T_TO_KG
    steel = _steel_tonnes(db, year)
    emp = _employees(db, year)
    return {
        "year": year,
        "total_emissions_tco2e": totals["total"],
        "steel_tonnes": round(steel, 0),
        "employees": emp,
        "intensity_kgco2e_per_tonne": round(emissions_kg / steel, 1) if steel else None,
        "intensity_tco2e_per_employee": round(totals["total"] / emp, 1) if emp else None,
    }


def hotspot(db: Session, year: int) -> dict:
    rows = (db.query(EmissionRecord.activity, EmissionRecord.scope,
                     func.sum(EmissionRecord.final_emissions))
            .filter(extract("year", EmissionRecord.activity_date) == year)
            .group_by(EmissionRecord.activity, EmissionRecord.scope)
            .order_by(func.sum(EmissionRecord.final_emissions).desc()).all())
    total = sum(v for *_, v in rows) or 1
    return {"year": year, "unit": "tCO2e", "total": round(total, 2),
            "sources": [{"source": a, "scope": int(s), "emissions": round(v, 2),
                         "share_pct": round(v / total * 100, 1)} for a, s, v in rows]}


def monthly_trend(db: Session, year: int) -> dict:
    rows = (db.query(extract("month", EmissionRecord.activity_date),
                     EmissionRecord.scope, func.sum(EmissionRecord.final_emissions))
            .filter(extract("year", EmissionRecord.activity_date) == year)
            .group_by(extract("month", EmissionRecord.activity_date), EmissionRecord.scope).all())
    s1 = [0.0] * 12; s2 = [0.0] * 12
    for m, s, v in rows:
        (s1 if int(s) == 1 else s2)[int(m) - 1] = round(v, 2)
    total = [round(a + b, 2) for a, b in zip(s1, s2)]
    return {"year": year, "unit": "tCO2e",
            "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
            "scope1": s1, "scope2": s2, "total": total}
