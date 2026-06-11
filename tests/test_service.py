"""Tests for src.tools.service CSV sync."""
import csv
import io

import pytest

from src.tools import service

HEADER = "date,servicer,odometer,what was done,interval (every x miles),next odometer + interval"
EXISTING_ROW = "2026-01-01,some shop,150000,oil change,3000,153000"


@pytest.fixture
def checklist_csv(tmp_path, monkeypatch):
    csv_path = tmp_path / "checklist.csv"
    # mirrors the real file: no trailing newline after the last row
    csv_path.write_text(f"{HEADER}\n{EXISTING_ROW}")
    monkeypatch.setattr(service, "CHECKLIST_CSV", csv_path)
    return csv_path


def test_append_checklist_row_adds_new_row_without_corrupting_existing(checklist_csv):
    service._append_checklist_row("2026-06-10", "self", 153500, "oil change", 3000, 156500)

    rows = list(csv.reader(io.StringIO(checklist_csv.read_text())))
    assert rows[0] == HEADER.split(",")
    assert rows[1] == EXISTING_ROW.split(",")
    assert rows[2] == ["2026-06-10", "self", "153500", "oil change", "3000", "156500"]


def test_append_checklist_row_handles_none_intervals_and_multiline_description(checklist_csv):
    service._append_checklist_row(
        "2026-06-15", "self", 153600, "transmission flush\nrear diff flush", None, None
    )

    rows = list(csv.reader(io.StringIO(checklist_csv.read_text())))
    new_row = rows[-1]
    assert new_row[3] == "transmission flush\nrear diff flush"
    assert new_row[4] == ""
    assert new_row[5] == ""
