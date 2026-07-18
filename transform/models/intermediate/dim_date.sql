{{ config(materialized='table') }}

-- Date spine for time-intelligence, one row per calendar day.
with spine as (
    select
        unnest(
            generate_series(date '2025-01-01', date '2027-12-31', interval '1 day')
        )::date as date_day
)

select
    date_day,
    year(date_day) as year,
    month(date_day) as month,
    day(date_day) as day,
    quarter(date_day) as quarter,
    dayofweek(date_day) as day_of_week,
    dayofweek(date_day) in (0, 6) as is_weekend
from spine
