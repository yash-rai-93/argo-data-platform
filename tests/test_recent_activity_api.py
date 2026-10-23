"""Serve real snapshot states and fail clearly if the bundle is missing."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import activity


def test_recent_activity_is_credential_free(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    snapshot = {
        "schema_version": 1,
        "status": "ready",
        "mode": "manual",
        "coverage_start": "2026-10-16",
        "through_exclusive": "2026-10-23",
        "event_count": 17,
    }
    path.write_text(json.dumps(snapshot))
    monkeypatch.setattr(activity, "_SNAPSHOT", path)
    app = FastAPI()
    app.include_router(activity.router)
    with TestClient(app) as client:
        response = client.get("/api/v1/activity/recent")
    assert response.status_code == 200
    assert response.json() == snapshot


def test_recent_activity_initial_state_and_missing_bundle(tmp_path, monkeypatch):
    path = tmp_path / "snapshot.json"
    monkeypatch.setattr(activity, "_SNAPSHOT", path)
    app = FastAPI()
    app.include_router(activity.router)
    with TestClient(app) as client:
        assert client.get("/api/v1/activity/recent").status_code == 503
        path.write_text(json.dumps({"status": "not_initialized", "mode": "manual"}))
        response = client.get("/api/v1/activity/recent")
        assert response.status_code == 200
        assert response.json()["status"] == "not_initialized"
        path.write_text("invalid json")
        assert client.get("/api/v1/activity/recent").status_code == 503
