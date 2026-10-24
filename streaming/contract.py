"""Replay envelope validation and a transactional, single-host audit sink."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from datetime import date, datetime
from pathlib import Path

from etl import pilot_activity as pilot
from etl import refresh_activity as refresh


def envelope(event, repository_id, state, state_hash, replay_id, published_at):
    return {
        "schema_version": 1,
        "mode": "historical_replay",
        "replay_id": replay_id,
        "source_state_sha256": state_hash,
        "coverage_start": state["coverage_start"],
        "through_exclusive": state["through_exclusive"],
        "published_at": published_at,
        "event": {**event, "repository_id": repository_id},
    }


def validate(raw, key, scope):
    if len(raw.encode()) > 16384:
        raise ValueError("message_too_large")
    value = json.loads(raw)
    if (
        type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["mode"] != "historical_replay"
        or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value["replay_id"])
        or not re.fullmatch(r"[a-f0-9]{64}", value["source_state_sha256"])
    ):
        raise ValueError("unsupported_envelope")
    published = datetime.fromisoformat(value["published_at"].replace("Z", "+00:00"))
    if published.tzinfo is None:
        raise ValueError("missing_publication_timezone")
    names = {r["repository_id"]: r["name"] for r in scope["repositories"]}
    row = value["event"]
    if key != row["event_id"]:
        raise ValueError("kafka_key_mismatch")
    start, end = (
        date.fromisoformat(value["coverage_start"]),
        date.fromisoformat(value["through_exclusive"]),
    )
    if not 0 < (end - start).days <= 90:
        raise ValueError("invalid_source_window")
    event = pilot.validate_row(row, names, start, end)
    if event["repo_name"] != row["repo_name"]:
        raise ValueError("repository_name_mismatch")
    return {**refresh.normalize_event(event), "repository_id": event["repository_id"]}


class Sink:
    """Atomic event-ID dedup and batch ledger; intentionally a bounded driver sink."""

    def __init__(self, path, contract):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.contract = contract
        with self.connect() as db:
            db.executescript(
                "create table if not exists config (id integer primary key, payload text);"
                "create table if not exists events (id text primary key, payload text);"
                "create table if not exists messages "
                "(topic text, part integer, offset integer, sha text, "
                "primary key(topic,part,offset));"
                "create table if not exists quarantine "
                "(topic text, part integer, offset integer, reason text, payload text, "
                "primary key(topic,part,offset));"
                "create table if not exists batches "
                "(id integer primary key, sha text, receipt text);"
            )
            pinned = pilot.canonical_json(contract).decode()
            old = db.execute("select payload from config where id=1").fetchone()
            if old and old[0] != pinned:
                raise ValueError("Sink contract changed; use a separate sink/checkpoint.")
            db.execute("insert or ignore into config values (1,?)", (pinned,))

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as db:
            with db:
                yield db

    def write(self, batch_id, rows, scope):
        rows = list(rows)
        if len(rows) > 20000:
            raise ValueError("Pilot batch exceeds 20000 records.")
        rows.sort(key=lambda r: (r["topic"], r["partition"], r["offset"]))
        fingerprint = hashlib.sha256(pilot.canonical_json(rows)).hexdigest()
        with self.connect() as db:
            db.execute("begin immediate")
            old = db.execute("select sha,receipt from batches where id=?", (batch_id,)).fetchone()
            if old:
                if old[0] != fingerprint:
                    raise ValueError("Batch ID was reused with different Kafka records.")
                return json.loads(old[1])
            receipt = {
                "batch_id": batch_id,
                "input_rows": len(rows),
                "new_ids": 0,
                "duplicate_ids": 0,
                "invalid_rows": 0,
            }
            for row in rows:
                raw, key = row["value"], row["key"]
                identity = (row["topic"], row["partition"], row["offset"])
                digest = hashlib.sha256(pilot.canonical_json([key, raw])).hexdigest()
                seen = db.execute(
                    "select sha from messages where topic=? and part=? and offset=?", identity
                ).fetchone()
                if seen and seen[0] != digest:
                    raise ValueError("Kafka offset content changed.")
                db.execute("insert or ignore into messages values (?,?,?,?)", (*identity, digest))
                try:
                    event = validate(raw, key, scope)
                    if (
                        row.get("event_day") is not None
                        and row["event_day"] != event["created_at"][:10]
                    ):
                        raise ValueError("spark_date_mismatch")
                except (ValueError, KeyError, TypeError, AttributeError) as error:
                    receipt["invalid_rows"] += 1
                    db.execute(
                        "insert or ignore into quarantine values (?,?,?,?,?)",
                        (*identity, type(error).__name__ + ":" + str(error)[:200], raw),
                    )
                    continue
                payload = pilot.canonical_json(event).decode()
                previous = db.execute(
                    "select payload from events where id=?", (event["event_id"],)
                ).fetchone()
                if previous and previous[0] != payload:
                    raise ValueError("Conflicting event ID; entire batch rolled back.")
                receipt["duplicate_ids" if previous else "new_ids"] += 1
                db.execute(
                    "insert or ignore into events values (?,?)", (event["event_id"], payload)
                )
            db.execute(
                "insert into batches values (?,?,?)",
                (
                    batch_id,
                    fingerprint,
                    json.dumps(receipt, sort_keys=True),
                ),
            )
            return receipt
