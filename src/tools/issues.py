"""Issue tracking tools."""
from datetime import date

from src.db import get_conn

VEHICLE_ID = 1


def get_issues(resolved: bool | None = None) -> str:
    """Return logged issues. Pass resolved=True for closed, False for open, None for all."""
    with get_conn() as conn:
        if resolved is None:
            rows = conn.execute(
                """
                SELECT id, logged_date, description, severity, dtc_code, conditions, resolved, resolution_notes
                FROM issues WHERE vehicle_id = %s ORDER BY logged_date DESC, id DESC
                """,
                (VEHICLE_ID,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, logged_date, description, severity, dtc_code, conditions, resolved, resolution_notes
                FROM issues WHERE vehicle_id = %s AND resolved = %s ORDER BY logged_date DESC, id DESC
                """,
                (VEHICLE_ID, resolved),
            ).fetchall()

    if not rows:
        return "No issues found."

    lines = [f"Issues ({len(rows)} records):"]
    for r in rows:
        dt = r["logged_date"].isoformat() if r["logged_date"] else "?"
        status = "resolved" if r["resolved"] else "open"
        dtc = f" | DTC: {r['dtc_code']}" if r["dtc_code"] else ""
        cond = f" | conditions: {r['conditions']}" if r["conditions"] else ""
        res = f" → {r['resolution_notes']}" if r["resolution_notes"] else ""
        lines.append(f"  #{r['id']} [{r['severity'].upper()}] {dt} | {status}{dtc}{cond}")
        lines.append(f"    {r['description']}{res}")
    return "\n".join(lines)


def log_issue(
    description: str,
    severity: str = "medium",
    dtc_code: str | None = None,
    conditions: str | None = None,
) -> str:
    """Log a new issue or symptom."""
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO issues (vehicle_id, logged_date, description, severity, dtc_code, conditions)
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s)
            RETURNING id
            """,
            (VEHICLE_ID, description, severity, dtc_code, conditions),
        ).fetchone()
        conn.commit()
        issue_id = row["id"]

    dtc_str = f" (DTC: {dtc_code})" if dtc_code else ""
    return f"Logged issue #{issue_id}: {description}{dtc_str}. Severity: {severity}."
