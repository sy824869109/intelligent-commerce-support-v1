"""Regeneration must not implicitly approve a changed published contract."""

import pytest

import check_contracts
from ics_contracts.routes import ROUTES


def test_design_document_matches_machine_route_table():
    document = (check_contracts.ROOT / "docs/api/m02-3-public-api-design.md").read_text(
        encoding="utf-8"
    )
    rows = {line.strip() for line in document.splitlines() if line.startswith("| ")}
    expected = {f"| {name} | {route['method']} {route['path']} |" for name, route in ROUTES.items()}
    actual = {line for line in rows if " /api/" in line or " /internal/" in line}
    assert actual == expected


def test_regeneration_cannot_replace_reviewed_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(check_contracts, "ROOT", tmp_path)
    monkeypatch.setattr(check_contracts, "BASELINE", tmp_path / "baseline.json")
    monkeypatch.setattr(check_contracts, "generated", lambda: {"contract.json": {"version": 1}})
    check_contracts.artifacts(write=True)
    check_contracts.compatibility(init=True)
    original = check_contracts.BASELINE.read_bytes()
    check_contracts.compatibility()
    with pytest.raises(FileExistsError):
        check_contracts.compatibility(init=True)
    monkeypatch.setattr(check_contracts, "generated", lambda: {"contract.json": {"version": 2}})
    with pytest.raises(ValueError, match="drift"):
        check_contracts.artifacts()
    check_contracts.artifacts(write=True)
    check_contracts.artifacts()
    with pytest.raises(ValueError, match="Frozen v1"):
        check_contracts.compatibility()
    assert check_contracts.BASELINE.read_bytes() == original
