"""FastAPI application for the GHG Emissions Reporting Platform."""
import os
from datetime import date
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database as D
import analytics as A
from calc import create_record, override_record, select_factor

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")
app = FastAPI(title="GHG Emissions Reporting Platform", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- schemas
class RecordIn(BaseModel):
    scope: int = Field(ge=1, le=2)
    activity: str
    quantity: float = Field(gt=0)
    activity_date: date
    section: str = ""

class OverrideIn(BaseModel):
    new_value: float = Field(ge=0)
    reason: str
    user: str = "analyst"

class MetricIn(BaseModel):
    date: date
    metric_name: str
    value: float
    unit: str = ""


# ---------------------------------------------------------------- lifecycle
def _ensure_data():
    """Create tables and seed demo data on first use. Runs at import so the app
    works regardless of how it's launched (uvicorn, gunicorn, tests)."""
    D.init_db()
    db = D.SessionLocal()
    try:
        if db.query(D.EmissionRecord).count() == 0:
            import seed
            seed.main()
    finally:
        db.close()


_ensure_data()


def _db():
    return D.SessionLocal()


# ---------------------------------------------------------------- core API (M3)
@app.get("/health")
def health():
    db = _db()
    try:
        return {"status": "ok", "records": db.query(D.EmissionRecord).count(),
                "factors": db.query(D.EmissionFactor).count(),
                "years": A.available_years(db)}
    finally:
        db.close()

@app.post("/records")
def add_record(body: RecordIn):
    db = _db()
    try:
        rec = create_record(db, scope=body.scope, activity=body.activity,
                            quantity=body.quantity, activity_date=body.activity_date,
                            section=body.section)
        return {"id": rec.id, "activity": rec.activity, "scope": rec.scope,
                "quantity": rec.quantity, "unit": rec.unit,
                "activity_date": rec.activity_date.isoformat(),
                "factor_id": rec.factor_id,
                "calculated_emissions_tco2e": round(rec.calculated_emissions, 3)}
    except ValueError as e:
        raise HTTPException(400, str(e))
    finally:
        db.close()

@app.post("/records/{record_id}/override")
def do_override(record_id: int, body: OverrideIn):
    db = _db()
    try:
        rec = override_record(db, record_id, body.new_value, body.reason, body.user)
        return {"id": rec.id, "final_emissions_tco2e": round(rec.final_emissions, 3),
                "is_overridden": rec.is_overridden}
    except ValueError as e:
        raise HTTPException(404, str(e))
    finally:
        db.close()

@app.get("/records")
def list_records(year: int | None = None, scope: int | None = None, limit: int = 100):
    db = _db()
    try:
        q = db.query(D.EmissionRecord)
        if year:
            from sqlalchemy import extract
            q = q.filter(extract("year", D.EmissionRecord.activity_date) == year)
        if scope:
            q = q.filter(D.EmissionRecord.scope == scope)
        rows = q.order_by(D.EmissionRecord.activity_date.desc()).limit(limit).all()
        return [{"id": r.id, "scope": r.scope, "activity": r.activity,
                 "quantity": r.quantity, "unit": r.unit,
                 "activity_date": r.activity_date.isoformat(),
                 "final_emissions_tco2e": round(r.final_emissions, 2),
                 "is_overridden": r.is_overridden} for r in rows]
    finally:
        db.close()

@app.get("/factors")
def list_factors(activity: str | None = None):
    db = _db()
    try:
        q = db.query(D.EmissionFactor)
        if activity:
            q = q.filter(D.EmissionFactor.activity == activity)
        rows = q.order_by(D.EmissionFactor.activity, D.EmissionFactor.valid_from).all()
        return [{"id": f.id, "activity": f.activity, "scope": f.scope, "unit": f.unit,
                 "co2e_per_unit": f.co2e_per_unit, "source": f.source,
                 "valid_from": f.valid_from.isoformat(),
                 "valid_to": f.valid_to.isoformat() if f.valid_to else None,
                 "version": f.version} for f in rows]
    finally:
        db.close()

@app.get("/audit")
def audit(record_id: int | None = None, limit: int = 50):
    db = _db()
    try:
        q = db.query(D.AuditLog)
        if record_id:
            q = q.filter(D.AuditLog.record_id == record_id)
        rows = q.order_by(D.AuditLog.created_at.desc()).limit(limit).all()
        return [{"id": a.id, "record_id": a.record_id, "action": a.action, "field": a.field,
                 "old_value": a.old_value, "new_value": a.new_value, "reason": a.reason,
                 "user": a.user, "at": a.created_at.isoformat()} for a in rows]
    finally:
        db.close()

@app.get("/metrics")
def get_metrics():
    db = _db()
    try:
        rows = db.query(D.BusinessMetric).order_by(D.BusinessMetric.date).all()
        return [{"date": m.date.isoformat(), "metric_name": m.metric_name,
                 "value": m.value, "unit": m.unit} for m in rows]
    finally:
        db.close()

@app.post("/metrics")
def add_metric(body: MetricIn):
    db = _db()
    try:
        m = D.BusinessMetric(date=body.date, metric_name=body.metric_name,
                             value=body.value, unit=body.unit)
        db.add(m); db.commit(); db.refresh(m)
        return {"id": m.id, "date": m.date.isoformat(), "metric_name": m.metric_name, "value": m.value}
    finally:
        db.close()


# ---------------------------------------------------------------- analytics (M2)
@app.get("/analytics/yoy")
def api_yoy():
    db = _db()
    try: return A.yoy(db)
    finally: db.close()

@app.get("/analytics/intensity")
def api_intensity(year: int | None = Query(None)):
    db = _db()
    try: return A.intensity(db, year or A.available_years(db)[-1])
    finally: db.close()

@app.get("/analytics/hotspot")
def api_hotspot(year: int | None = Query(None)):
    db = _db()
    try: return A.hotspot(db, year or A.available_years(db)[-1])
    finally: db.close()

@app.get("/analytics/monthly")
def api_monthly(year: int | None = Query(None)):
    db = _db()
    try: return A.monthly_trend(db, year or A.available_years(db)[-1])
    finally: db.close()

@app.get("/api")
def api_root():
    return {"service": "GHG Emissions Reporting Platform",
            "endpoints": ["/health", "/records", "/factors", "/audit", "/metrics",
                          "/analytics/yoy", "/analytics/intensity", "/analytics/hotspot",
                          "/analytics/monthly", "/docs"]}

# dashboard (mounted last so API routes win)
app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="dashboard")
