-- Singular test: no feature in ml_contributor_churn_training may carry signal
-- from on or after observation_end.
--
-- The mart stores aggregates, not the events behind them, so checking the
-- columns alone would only catch impossible values. This recomputes the
-- aggregates from raw_github_events restricted to the observation window and
-- compares them to what the mart published. A disagreement means the mart
-- counted an event it should not have seen.
--
-- dbt singular tests pass when the query returns zero rows.

with bounds as (

    select
        date '2023-07-01' as observation_start,
        date '2023-11-01' as observation_end

),

events as (

    -- Same dedupe as the mart. Without it, replayed events inflate the
    -- recomputed counts and this test fails on its own arithmetic.
    select
        event_id,
        actor_login,
        created_at
    from {{ source('github_archive', 'raw_github_events') }}
    qualify row_number() over (
        partition by event_id order by created_at
    ) = 1

),

observation as (

    select e.*
    from events as e
    cross join bounds as b
    where e.created_at >= b.observation_start
        and e.created_at < b.observation_end

),

recomputed as (

    select
        o.actor_login,
        count(*) as total_events,
        min(o.created_at) as first_event_at,
        max(o.created_at) as last_event_at
    from observation as o
    group by o.actor_login

)

select
    m.actor_login,
    m.total_events as mart_total_events,
    r.total_events as window_total_events,
    m.first_event_at as mart_first_event_at,
    r.first_event_at as window_first_event_at,
    m.days_since_last_event as mart_days_since_last_event,
    date_diff('day', r.last_event_at, b.observation_end) as window_days_since_last_event,
    m.tenure_days
from {{ ref('ml_contributor_churn_training') }} as m
inner join recomputed as r on m.actor_login = r.actor_login
cross join bounds as b
where
    -- Volume must come entirely from inside the window.
    m.total_events != r.total_events

    -- Entry and exit timestamps must be the window's, not the target's.
    or m.first_event_at != r.first_event_at

    -- Recency is anchored to the window edge. Anchoring it to max(created_at)
    -- instead would pull the target window into a feature; this catches that.
    or m.days_since_last_event != date_diff('day', r.last_event_at, b.observation_end)

    -- A negative recency means the last observed event fell after
    -- observation_end, which is leakage by definition.
    or m.days_since_last_event < 0

    -- Tenure runs from first event to the window edge, so it cannot be negative
    -- and cannot exceed the window itself.
    or m.tenure_days < 0
    or m.tenure_days > date_diff('day', b.observation_start, b.observation_end)

    -- No contributor may enter the cohort outside the observation window.
    or m.first_event_at < b.observation_start
    or m.first_event_at >= b.observation_end
