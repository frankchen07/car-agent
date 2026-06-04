"""Import canonical CSVs into Postgres. Idempotent (truncates and reloads)."""
import os
import sys
from pathlib import Path
import pandas as pd
import psycopg
from dotenv import load_dotenv

load_dotenv()

CANONICAL = Path(__file__).parent.parent / "knowledge" / "sources" / "canonical"
VEHICLE_ID = 1
CURRENT_MILEAGE = 153_000


def parse_int(val) -> int | None:
    """Return int if val is a plain integer string, else None."""
    try:
        return int(str(val).strip().replace(",", ""))
    except (ValueError, TypeError):
        return None


def seed(conn: psycopg.Connection) -> None:
    # -- vehicle ---------------------------------------------------------------
    conn.execute("TRUNCATE issues, service_events, maintenance_rules, oem_parts, vehicles RESTART IDENTITY CASCADE")

    conn.execute(
        """INSERT INTO vehicles (year, make, model, trim, engine, current_mileage, notes)
           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
        (
            2003, "Subaru", "Impreza WRX", "WRX", "EJ205 DOHC Turbo (engine rebuild 2026)",
            CURRENT_MILEAGE,
            "3rd owner since 2019. Engine remachined head + new bottom block @ 150,181 mi (March 2026). P0301/P0303 misfires history.",
        ),
    )
    print("vehicle inserted")

    # -- service_events --------------------------------------------------------
    checklist = pd.read_csv(
        CANONICAL / "subaru-impreza-wrx-2003-maintenance-checklist.csv",
        dtype=str,
        keep_default_na=False,
    )

    rows = 0
    for _, row in checklist.iterrows():
        date_val = row["date"].strip() or None
        try:
            # basic date validation
            pd.to_datetime(date_val)
        except Exception:
            date_val = None

        odometer = parse_int(row["odometer"])
        interval = parse_int(row["interval (every x miles)"])
        next_due = parse_int(row["next odometer + interval"])
        description = row["what was done"].strip()
        servicer = row["servicer"].strip() or None

        conn.execute(
            """INSERT INTO service_events
               (vehicle_id, service_date, mileage, servicer, description, interval_miles, next_due_mileage, source)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (VEHICLE_ID, date_val, odometer, servicer, description, interval, next_due, "checklist_import"),
        )
        rows += 1
    print(f"service_events: {rows} rows")

    # -- maintenance_rules -----------------------------------------------------
    plan = pd.read_csv(
        CANONICAL / "maintenance-plan.csv",
        dtype=str,
        keep_default_na=False,
    )

    rows = 0
    for _, row in plan.iterrows():
        conn.execute(
            """INSERT INTO maintenance_rules
               (vehicle_id, item, category, anchor_mileage, interval_miles, due_mileage, priority, status, notes)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                VEHICLE_ID,
                row["item"].strip(),
                row["category"].strip() or None,
                parse_int(row["anchor_mileage"]),
                parse_int(row["interval_miles"]),
                parse_int(row["due_mileage"]),
                row["priority"].strip() or None,
                row["status"].strip() or "active",
                row["notes"].strip() or None,
            ),
        )
        rows += 1
    print(f"maintenance_rules: {rows} rows")

    # -- oem_parts -------------------------------------------------------------
    parts = pd.read_csv(
        CANONICAL / "subaru-impreza-wrx-2003-official-oem-parts.csv",
        dtype=str,
        keep_default_na=False,
    )

    rows = 0
    for _, row in parts.iterrows():
        part_cat = row["part"].strip()
        part_num = row["name or oem part number"].strip()
        if not part_cat:
            continue
        conn.execute(
            "INSERT INTO oem_parts (vehicle_id, part_category, part_number) VALUES (%s, %s, %s)",
            (VEHICLE_ID, part_cat, part_num or None),
        )
        rows += 1
    print(f"oem_parts: {rows} rows")

    conn.commit()
    print("seed complete")


if __name__ == "__main__":
    db_url = os.environ["DATABASE_URL"]
    with psycopg.connect(db_url) as conn:
        seed(conn)
