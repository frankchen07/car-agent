"""Service history and maintenance plan tools."""
import csv
from datetime import date
from pathlib import Path

from src.db import get_conn

VEHICLE_ID = 1
CHECKLIST_CSV = (
    Path(__file__).resolve().parents[2]
    / "knowledge" / "sources" / "canonical" / "subaru-impreza-wrx-2003-maintenance-checklist.csv"
)


def get_service_history(limit: int = 20, keyword: str | None = None) -> str:
    """Query service history from the database. Optionally filter by keyword."""
    with get_conn() as conn:
        if keyword:
            rows = conn.execute(
                """
                SELECT service_date, mileage, servicer, description, interval_miles, next_due_mileage
                FROM service_events
                WHERE vehicle_id = %s AND description ILIKE %s
                ORDER BY service_date DESC, id DESC
                LIMIT %s
                """,
                (VEHICLE_ID, f"%{keyword}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT service_date, mileage, servicer, description, interval_miles, next_due_mileage
                FROM service_events
                WHERE vehicle_id = %s
                ORDER BY service_date DESC, id DESC
                LIMIT %s
                """,
                (VEHICLE_ID, limit),
            ).fetchall()

    if not rows:
        return "No service history found."

    lines = [f"Service history ({len(rows)} records):"]
    for r in rows:
        dt = r["service_date"].isoformat() if r["service_date"] else "?"
        mi = f"{r['mileage']:,}" if r["mileage"] else "?"
        next_due = f" → next due {r['next_due_mileage']:,} mi" if r["next_due_mileage"] else ""
        lines.append(f"  {dt} | {mi} mi | {r['servicer'] or '?'} | {r['description']}{next_due}")
    return "\n".join(lines)


def get_maintenance_plan(current_mileage: int) -> str:
    """Return upcoming and overdue maintenance items based on current mileage."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT item, category, due_mileage, priority, status, notes,
                   (due_mileage - %s) AS miles_remaining
            FROM maintenance_rules
            WHERE vehicle_id = %s AND status != 'completed'
            ORDER BY due_mileage ASC
            """,
            (current_mileage, VEHICLE_ID),
        ).fetchall()

    if not rows:
        return "No active maintenance items found."

    overdue = [r for r in rows if r["miles_remaining"] is not None and r["miles_remaining"] <= 0]
    upcoming = [r for r in rows if r["miles_remaining"] is None or r["miles_remaining"] > 0]

    lines = [f"Maintenance plan at {current_mileage:,} mi:"]

    if overdue:
        lines.append("\nOVERDUE:")
        for r in overdue:
            gap = abs(r["miles_remaining"])
            due = r["due_mileage"]
            due_str = f"{due:,} mi" if due is not None else "TBD"
            notes = f" — {r['notes']}" if r["notes"] else ""
            lines.append(f"  [{r['priority'].upper()}] {r['item']} | due {due_str} ({gap:,} mi overdue){notes}")

    if upcoming:
        lines.append("\nUPCOMING:")
        for r in upcoming:
            remaining = r["miles_remaining"]
            due = r["due_mileage"]
            due_str = f"{due:,} mi" if due is not None else "TBD"
            mi_str = f"{remaining:,} mi away" if remaining is not None else "unknown"
            notes = f" — {r['notes']}" if r["notes"] else ""
            lines.append(f"  [{r['priority'].upper()}] {r['item']} | due {due_str} ({mi_str}){notes}")

    return "\n".join(lines)


def _append_checklist_row(
    service_date: str,
    servicer: str,
    mileage: int,
    description: str,
    interval_miles: int | None,
    next_due_mileage: int | None,
) -> None:
    """Append a row to the canonical maintenance checklist CSV (source of truth for seed_db.py)."""
    with open(CHECKLIST_CSV, "rb") as f:
        f.seek(-1, 2)
        ends_with_newline = f.read(1) == b"\n"

    with open(CHECKLIST_CSV, "a", newline="") as f:
        if not ends_with_newline:
            f.write("\n")
        csv.writer(f, lineterminator="\n").writerow([
            service_date,
            servicer,
            mileage,
            description,
            "" if interval_miles is None else interval_miles,
            "" if next_due_mileage is None else next_due_mileage,
        ])


def log_service(
    service_date: str,
    mileage: int,
    servicer: str,
    description: str,
    interval_miles: int | None = None,
    next_due_mileage: int | None = None,
) -> str:
    """Log a service event and optionally update the relevant maintenance rule."""
    parsed_date = date.fromisoformat(service_date)

    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO service_events
              (vehicle_id, service_date, mileage, servicer, description, interval_miles, next_due_mileage, source)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'agent_log')
            RETURNING id
            """,
            (VEHICLE_ID, parsed_date, mileage, servicer, description, interval_miles, next_due_mileage),
        ).fetchone()
        event_id = row["id"]

        if next_due_mileage:
            desc_lower = description.lower()
            rules = conn.execute(
                "SELECT id, item FROM maintenance_rules WHERE vehicle_id = %s AND status = 'active'",
                (VEHICLE_ID,),
            ).fetchall()
            for rule in rules:
                if any(word in desc_lower for word in rule["item"].lower().split()[:3]):
                    conn.execute(
                        "UPDATE maintenance_rules SET anchor_mileage = %s, due_mileage = %s WHERE id = %s",
                        (mileage, next_due_mileage, rule["id"]),
                    )
                    break

        # Append to the canonical CSV before committing: if the file write fails,
        # the exception aborts the transaction so the DB and CSV stay in sync.
        _append_checklist_row(service_date, servicer, mileage, description, interval_miles, next_due_mileage)

        conn.commit()

    return (
        f"Logged service event #{event_id}: {description} at {mileage:,} mi on {service_date}. "
        f"Appended to maintenance-checklist.csv."
    )
