"""Churn feature extraction from the DuckDB warehouse."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import duckdb
import pandas as pd

_TRANSFORM_DIR = Path(__file__).resolve().parents[1] / "transform"
_DB_PATH = _TRANSFORM_DIR / "argo.duckdb"


@contextmanager
def _working_dir(path: Path) -> Iterator[None]:
    """Run inside ``path`` so DuckDB views resolve their relative source paths."""
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class ChurnFeatureExtractor:
    """Builds a per-user churn training frame from the warehouse marts."""

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path

    def extract_features(self) -> pd.DataFrame:
        """Return per-user features and a leakage-free ``is_churned`` target.

        Features are drawn from the observation window (sessions before a cutoff
        30 days short of the data's end). A user is churned when they have no
        sessions in the 30-day label window that follows the cutoff.
        """
        query = """
            with bounds as (
                select max(event_timestamp) - interval '30 days' as cutoff_date
                from stg_events
            ),

            population as (
                select u.user_id, u.first_seen_at
                from dim_users as u, bounds as b
                where u.first_seen_at < b.cutoff_date
            ),

            pre_sessions as (
                select
                    s.user_id,
                    count(*) as total_sessions,
                    avg(s.duration_seconds) as avg_session_duration
                from int_sessions as s, bounds as b
                where s.session_start_at < b.cutoff_date
                group by s.user_id
            ),

            post_sessions as (
                select distinct s.user_id
                from int_sessions as s, bounds as b
                where s.session_start_at >= b.cutoff_date
                    and s.session_start_at < b.cutoff_date + interval '30 days'
            )

            select
                p.user_id,
                coalesce(pre.total_sessions, 0) as total_sessions,
                coalesce(pre.avg_session_duration, 0) as avg_session_duration,
                date_diff('day', p.first_seen_at, b.cutoff_date) as account_age_days,
                case when post.user_id is null then 1 else 0 end as is_churned
            from population as p
            cross join bounds as b
            left join pre_sessions as pre on p.user_id = pre.user_id
            left join post_sessions as post on p.user_id = post.user_id
        """
        with _working_dir(self.db_path.parent):
            con = duckdb.connect(str(self.db_path))
            try:
                return con.execute(query).df()
            finally:
                con.close()
