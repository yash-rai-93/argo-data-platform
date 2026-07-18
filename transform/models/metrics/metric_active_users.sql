-- Daily active-user metrics. DuckDB has no windowed COUNT(DISTINCT), so rolling
-- WAU/MAU are computed by joining each day to the trailing 7-/30-day user set.
with daily_users as (
    select distinct
        user_id,
        date_trunc('day', session_start_at) as activity_date
    from {{ ref('fact_sessions') }}
),

calendar as (
    select distinct activity_date from daily_users
)

select
    c.activity_date,
    count(distinct case
        when d.activity_date = c.activity_date then d.user_id
    end) as dau,
    count(distinct case
        when
            d.activity_date > c.activity_date - interval '7 days'
            then d.user_id
    end) as wau,
    count(distinct d.user_id) as mau
from calendar as c
inner join daily_users as d
    on
        d.activity_date between c.activity_date
        - interval '29 days' and c.activity_date
group by c.activity_date
order by c.activity_date
