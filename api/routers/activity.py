"""Read the promoted recent snapshot without cloud calls or runtime credentials."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/activity", tags=["activity"])
_SNAPSHOT = Path(__file__).resolve().parents[2] / "data" / "recent-activity.json"


@router.get("/recent")
def recent_activity() -> dict:
    """Return explicit freshness; historical model metrics remain independent."""
    try:
        snapshot = json.loads(_SNAPSHOT.read_text())
        if snapshot["status"] not in ("not_initialized", "ready"):
            raise ValueError("Unsupported snapshot status.")
        return snapshot
    except (OSError, ValueError, KeyError) as error:
        raise HTTPException(status_code=503, detail="Recent activity snapshot unavailable.") from error
