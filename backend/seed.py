"""
Pre-populate the database with realistic, demo-ready data for an integrated steel
plant (inspired by the provided GHG_Sheet_.xlsx: same plant, sections and source
types, with figures scaled to a believable ~11 MtCO2e/year).

What it creates:
  - emission_factors : every source has a 2023 version (now EXPIRED) and a 2024
    version (current); two sources also carry a 2022 version -> multiple versions
    so historical accuracy and "expired factors for past years" are demonstrable.
  - emission_records : monthly records for ALL of 2023 and 2024, created THROUGH
    the calc engine so each picks the factor valid on its own date.
  - business_metrics : monthly tonnes of steel + yearly headcount (for intensity).
"""
from __future__ import annotations
import os, math, random
from datetime import date
import database as D
from calc import create_record

random.seed(42)

# source, scope, unit, qty_2024(annual), f2022, f2023, f2024, citation
SOURCES = [
    ("Coking Coal",        1, "tonnes", 1_800_000, 2.48, 2.45, 2.42, "IPCC 2006 Guidelines"),
    ("Coke",               1, "tonnes",   380_000, 3.12, 3.10, 3.08, "IPCC 2006 Guidelines"),
    ("Process Gases",      1, "kNm3",     700_000, None, 1.80, 1.78, "Worldsteel CO2 Methodology"),
    ("Natural Gas",        1, "kNm3",     350_000, None, 2.42, 2.40, "IPCC 2006 Guidelines"),
    ("Fluxes",             1, "tonnes", 1_300_000, None, 0.43, 0.44, "IPCC 2006 (calcination)"),
    ("Ferroalloys",        1, "tonnes",   180_000, None, 2.10, 2.12, "IPCC 2006 Guidelines"),
    ("Diesel & Fuel Oils", 1, "KL",         90_000, None, 2.65, 2.68, "IPCC 2006 Guidelines"),
    ("Alternative Fuels",  1, "tonnes",   150_000, None, 1.90, 1.85, "GHG Protocol"),
    ("Grid Electricity",   2, "MWh",     2_600_000, 0.74, 0.72, 0.71, "CEA India CO2 Database 2024"),
    ("Imported Steam",     2, "tonnes",   350_000, None, 0.20, 0.19, "Supplier disclosure"),
]
# mild monthly seasonality (maintenance shutdowns in monsoon -> lower mid-year)
SEASON = [1.05, 1.03, 1.04, 1.00, 0.98, 0.94, 0.92, 0.95, 0.99, 1.03, 1.04, 1.03]


def seed_factors(db):
    for name, scope, unit, _q, f22, f23, f24, cite in SOURCES:
        if f22 is not None:
            db.add(D.EmissionFactor(activity=name, scope=scope, unit=unit, co2e_per_unit=f22,
                   source=cite, valid_from=date(2022, 1, 1), valid_to=date(2022, 12, 31), version=1))
        db.add(D.EmissionFactor(activity=name, scope=scope, unit=unit, co2e_per_unit=f23,
               source=cite, valid_from=date(2023, 1, 1), valid_to=date(2023, 12, 31),
               version=2 if f22 is not None else 1))
        db.add(D.EmissionFactor(activity=name, scope=scope, unit=unit, co2e_per_unit=f24,
               source=cite, valid_from=date(2024, 1, 1), valid_to=None,
               version=3 if f22 is not None else 2))
    db.commit()


def seed_records(db):
    for name, scope, unit, q2024, *_ in SOURCES:
        for year, growth in [(2023, 0.93), (2024, 1.00)]:     # plant grew ~7% YoY
            annual = q2024 * growth
            for m in range(1, 13):
                qty = annual / 12 * SEASON[m - 1] * random.uniform(0.97, 1.03)
                create_record(db, scope=scope, activity=name, quantity=round(qty, 2),
                              activity_date=date(year, m, 15), section="", unit=unit)


def seed_metrics(db):
    steel_2024 = 5_000_000
    for year, growth in [(2023, 0.92), (2024, 1.00)]:
        for m in range(1, 13):
            val = steel_2024 * growth / 12 * SEASON[m - 1] * random.uniform(0.98, 1.02)
            db.add(D.BusinessMetric(date=date(year, m, 28), metric_name="Tonnes of Steel Produced",
                                    value=round(val, 0), unit="tonnes"))
    db.add(D.BusinessMetric(date=date(2023, 12, 31), metric_name="Number of Employees", value=12000, unit="people"))
    db.add(D.BusinessMetric(date=date(2024, 12, 31), metric_name="Number of Employees", value=12500, unit="people"))
    db.commit()


def main():
    D.reset_db()
    db = D.SessionLocal()
    try:
        seed_factors(db)
        seed_records(db)
        seed_metrics(db)
        nf = db.query(D.EmissionFactor).count()
        nr = db.query(D.EmissionRecord).count()
        na = db.query(D.AuditLog).count()
        nm = db.query(D.BusinessMetric).count()
        print(f"Seeded: {nf} factors | {nr} records | {na} audit rows | {nm} business metrics")
    finally:
        db.close()


if __name__ == "__main__":
    main()
