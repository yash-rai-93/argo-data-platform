"""STL decomposition and anomaly detection over daily GitHub activity.

Open-source contribution volume is not stationary. It carries a strong weekly
seasonal component -- weekday commits vastly outnumber weekend ones -- layered
on a slow-moving trend. Flagging raw daily spikes without removing that
structure just rediscovers Saturday every week.

STL (Seasonal-Trend decomposition using Loess) separates the series into
trend + seasonal + residual. Anomalies are then defined on the residual alone:
days whose activity cannot be explained by either the level of the project or
the day of the week. Those are the real events -- a CVE scramble, a major
release, a holiday shutdown.

Writes ``main.metric_activity_decomposition`` for the API to serve. This is a
Python-side mart, not a dbt model, because STL has no SQL equivalent; the table
is registered from Arrow so dbt's own models are untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import duckdb
import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
_DB_PATH: Final[Path] = _ROOT / "transform" / "argo.duckdb"
_SOURCE_TABLE: Final[str] = "main.raw_github_events"
_TARGET_TABLE: Final[str] = "main.metric_activity_decomposition"
_PERIOD: Final[int] = 7
_ANOMALY_SIGMA: Final[float] = 3.0


def load_daily_counts() -> pd.DataFrame:
    """Return one row per calendar day with total events and contributors.

    Aggregation happens in DuckDB so only ~184 rows cross the boundary rather
    than 547k. The final partial day is dropped: a truncated day always reads
    as a catastrophic residual.
    """
    connection = duckdb.connect(str(_DB_PATH), read_only=True)
    try:
        frame: pd.DataFrame = connection.execute(
            f"""
            select
                cast(created_at as date) as activity_date,
                count(*) as observed,
                count(distinct actor_login) as contributors
            from {_SOURCE_TABLE}
            where cast(created_at as date) < (
                select max(cast(created_at as date)) from {_SOURCE_TABLE}
            )
            group by cast(created_at as date)
            order by activity_date asc
            """
        ).df()
    finally:
        connection.close()
    return frame


def decompose(frame: pd.DataFrame) -> pd.DataFrame:
    """Run STL and mark residual outliers beyond the sigma threshold.

    ``robust=True`` uses iteratively reweighted Loess so that a single extreme
    day cannot drag the trend toward itself and mask its own anomaly.
    """
    if len(frame) < _PERIOD * 2:
        raise SystemExit(
            f"Need at least {_PERIOD * 2} daily observations for STL, got {len(frame)}."
        )

    series = pd.Series(
        frame["observed"].to_numpy(dtype="float64"),
        index=pd.DatetimeIndex(frame["activity_date"]),
    ).asfreq("D")
    series = series.interpolate(limit_direction="both")

    result = STL(series, period=_PERIOD, robust=True).fit()

    residual: np.ndarray = np.asarray(result.resid)
    sigma: float = float(np.std(residual))
    threshold: float = _ANOMALY_SIGMA * sigma

    decomposed = pd.DataFrame(
        {
            "activity_date": series.index.date,
            "observed": series.to_numpy(),
            "trend": np.asarray(result.trend),
            "seasonal": np.asarray(result.seasonal),
            "residual": residual,
            "residual_zscore": residual / sigma if sigma > 0 else residual,
            "is_anomaly": np.abs(residual) > threshold,
        }
    )
    decomposed["contributors"] = frame["contributors"].to_numpy()
    return decomposed


def persist(frame: pd.DataFrame) -> None:
    """Replace the decomposition table via a zero-copy Arrow registration."""
    connection = duckdb.connect(str(_DB_PATH))
    try:
        connection.register("decomposition_arrow", frame)
        connection.execute(
            f"create or replace table {_TARGET_TABLE} as select * from decomposition_arrow"
        )
    finally:
        connection.close()


def main() -> None:
    """Decompose daily activity, flag anomalies, and persist the result."""
    daily: pd.DataFrame = load_daily_counts()
    if daily.empty:
        raise SystemExit(f"{_SOURCE_TABLE} is empty; run etl/land_github_data.py first.")

    decomposed: pd.DataFrame = decompose(daily)
    anomalies: pd.DataFrame = decomposed.loc[decomposed["is_anomaly"]]

    print(f"Days analysed:    {len(decomposed)}")
    print(f"Seasonal period:  {_PERIOD}")
    print(f"Residual sigma:   {float(np.std(decomposed['residual'])):.2f}")
    print(f"Anomalies flagged: {len(anomalies)} at {_ANOMALY_SIGMA} sigma")
    for row in anomalies.itertuples():
        direction = "spike" if row.residual > 0 else "collapse"
        print(
            f"  {row.activity_date}  {direction:<8} "
            f"observed={row.observed:>7.0f}  z={row.residual_zscore:+.2f}"
        )

    persist(decomposed)
    print(f"Saved {_TARGET_TABLE}")


if __name__ == "__main__":
    main()
