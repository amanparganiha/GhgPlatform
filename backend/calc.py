"""
Emission calculation engine.

Core formula:  Activity Data x Emission Factor = GHG Emissions (tCO2e)

Historical accuracy: the factor chosen is the one VALID ON THE ACTIVITY DATE, not
simply the latest one. This is the difference between recomputing 2023 emissions
with a stale 2024 factor (wrong) and with the factor that actually applied in 2023.
"""
from __future__ import annotations
from datetime import date
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import EmissionFactor, EmissionRecord, AuditLog


def select_factor(db: Session, activity: str, scope: int, activity_date: date) -> EmissionFactor | None:
    """Return the emission factor valid for `activity_date` (historical accuracy)."""
    stmt = (select(EmissionFactor)
            .where(EmissionFactor.activity == activity,
                   EmissionFactor.scope == scope,
                   EmissionFactor.valid_from <= activity_date)
            .order_by(EmissionFactor.valid_from.desc(), EmissionFactor.version.desc()))
    for f in db.scalars(stmt):
        if f.valid_to is None or f.valid_to >= activity_date:
            return f
    return None


def create_record(db: Session, *, scope: int, activity: str, quantity: float,
                  activity_date: date, section: str = "", location: str = "Central Steel Plant",
                  unit: str | None = None) -> EmissionRecord:
    """Create an emission record, auto-selecting the date-valid factor and computing emissions."""
    factor = select_factor(db, activity, scope, activity_date)
    if factor is None:
        raise ValueError(f"No emission factor for activity='{activity}' scope={scope} "
                         f"valid on {activity_date}")
    emissions = quantity * factor.co2e_per_unit          # tCO2e
    rec = EmissionRecord(
        scope=scope, activity=activity, section=section, location=location,
        factor_id=factor.id, quantity=quantity, unit=unit or factor.unit,
        activity_date=activity_date, calculated_emissions=emissions,
        final_emissions=emissions, is_overridden=False)
    db.add(rec)
    db.flush()
    db.add(AuditLog(record_id=rec.id, action="create", field="calculated_emissions",
                    old_value="", new_value=f"{emissions:.3f}",
                    reason=f"factor v{factor.version} ({factor.co2e_per_unit} {factor.unit}) "
                           f"valid {factor.valid_from}..{factor.valid_to or 'current'}",
                    user="system"))
    db.commit()
    db.refresh(rec)
    return rec


def override_record(db: Session, record_id: int, new_value: float, reason: str,
                    user: str = "analyst") -> EmissionRecord:
    """Manually override a record's emissions, writing a full audit trail entry."""
    rec = db.get(EmissionRecord, record_id)
    if rec is None:
        raise ValueError(f"record {record_id} not found")
    old = rec.final_emissions
    rec.final_emissions = new_value
    rec.is_overridden = True
    db.add(AuditLog(record_id=rec.id, action="override", field="final_emissions",
                    old_value=f"{old:.3f}", new_value=f"{new_value:.3f}",
                    reason=reason, user=user))
    db.commit()
    db.refresh(rec)
    return rec
