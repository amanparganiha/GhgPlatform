"""
Database layer for the GHG Emissions Reporting Platform.

Four master-data tables, exactly as the brief specifies:
  - emission_factors : VERSIONED factors with validity dates (valid_from/valid_to).
  - emission_records : each recorded emission, linked to the factor actually used.
  - audit_log        : every manual override, with before/after values.
  - business_metrics : key business metrics over time (e.g. tonnes of steel).
"""
from __future__ import annotations
import os
from datetime import date, datetime
from sqlalchemy import (create_engine, String, Integer, Float, Date, DateTime,
                        Boolean, ForeignKey, func)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column, relationship,
                            sessionmaker)

DB_PATH = os.environ.get("GHG_DB", os.path.join(os.path.dirname(__file__), "..", "data", "ghg.db"))
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)


class Base(DeclarativeBase):
    pass


class EmissionFactor(Base):
    __tablename__ = "emission_factors"
    id: Mapped[int] = mapped_column(primary_key=True)
    activity: Mapped[str] = mapped_column(String, index=True)       # e.g. "Diesel", "Grid Electricity"
    scope: Mapped[int] = mapped_column(Integer, index=True)         # 1 or 2
    unit: Mapped[str] = mapped_column(String)                       # activity unit (tonnes, kWh, KL...)
    co2e_per_unit: Mapped[float] = mapped_column(Float)             # tCO2e per unit
    source: Mapped[str] = mapped_column(String)                     # citation
    valid_from: Mapped[date] = mapped_column(Date, index=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)  # None = still current
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    records: Mapped[list["EmissionRecord"]] = relationship(back_populates="factor")


class EmissionRecord(Base):
    __tablename__ = "emission_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[int] = mapped_column(Integer, index=True)
    activity: Mapped[str] = mapped_column(String, index=True)
    section: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str] = mapped_column(String, default="Central Steel Plant")
    factor_id: Mapped[int | None] = mapped_column(ForeignKey("emission_factors.id"), nullable=True)
    quantity: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
    activity_date: Mapped[date] = mapped_column(Date, index=True)
    calculated_emissions: Mapped[float] = mapped_column(Float)      # quantity * factor (tCO2e)
    final_emissions: Mapped[float] = mapped_column(Float)           # = calculated unless overridden
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    factor: Mapped["EmissionFactor"] = relationship(back_populates="records")
    audits: Mapped[list["AuditLog"]] = relationship(back_populates="record")


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    record_id: Mapped[int] = mapped_column(ForeignKey("emission_records.id"))
    action: Mapped[str] = mapped_column(String)                     # "create" | "override"
    field: Mapped[str] = mapped_column(String)
    old_value: Mapped[str] = mapped_column(String, default="")
    new_value: Mapped[str] = mapped_column(String, default="")
    reason: Mapped[str] = mapped_column(String, default="")
    user: Mapped[str] = mapped_column(String, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    record: Mapped["EmissionRecord"] = relationship(back_populates="audits")


class BusinessMetric(Base):
    __tablename__ = "business_metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    metric_name: Mapped[str] = mapped_column(String, index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String, default="")


def init_db():
    Base.metadata.create_all(engine)


def reset_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
