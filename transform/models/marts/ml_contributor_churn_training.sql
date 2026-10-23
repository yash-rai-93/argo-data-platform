{{ config(materialized='table') }}

-- Leakage-free contributor churn training set.
-- Features are computed strictly inside the observation window; the label is
-- computed strictly inside the disjoint target window. Both intervals are
-- half-open [start, end) so no event can be counted on both sides of the cut.

with bounds as (

    -- Midpoint and recency cutoff are derived, not hardcoded, so moving the
    -- window boundaries above automatically moves the trajectory splits too.
    select
        observation_start,
        observation_end,
        target_end,
        observation_start + to_days(
            cast(
                date_diff('day', observation_start, observation_end) / 2
                as integer
            )
        ) as observation_midpoint,
        observation_end - to_days(30) as observation_last_30
    from (
        select
            date '2023-07-01' as observation_start,
            date '2023-11-01' as observation_end,
            date '2024-01-01' as target_end
    ) as study_window

),

events as (

    -- GitHub Archive replays events, so dedupe on the immutable event id.
    select
        event_id,
        event_category,
        actor_login,
        repo_name,
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
    where
        e.created_at >= b.observation_start
        and e.created_at < b.observation_end

),

target as (

    -- Survivors: contributors seen again inside the target window. max() is
    -- their last observed activity, which is where right-censoring occurs.
    select
        e.actor_login,
        max(e.created_at) as last_target_event_at
    from events as e
    cross join bounds as b
    where
        e.created_at >= b.observation_end
        and e.created_at < b.target_end
    group by e.actor_login

),

features as (

    select
        o.actor_login,
        min(o.created_at) as first_event_at,
        max(o.created_at) as last_event_at,
        count(*) as total_events,
        count(distinct o.repo_name) as distinct_repos,
        count(distinct cast(o.created_at as date)) as active_days,
        count(*) filter (where o.event_category = 'commit') as commit_events,
        count(*) filter (where o.event_category = 'pull_request')
            as pull_request_events,
        count(*) filter (where o.event_category = 'issue') as issue_events,
        count(*) filter (where o.event_category = 'comment') as comment_events,
        count(*) filter (where o.event_category = 'engagement')
            as engagement_events,
        count(*) filter (where o.event_category = 'release') as release_events,
        count(*) filter (where dayofweek(o.created_at) in (0, 6))
            as weekend_events,
        -- Trajectory counters. A single pass over the same grouped scan, so
        -- these cost no extra joins and no extra window materialisation.
        count(*) filter (where o.created_at >= b.observation_last_30)
            as events_last_30_days,
        count(*) filter (where o.created_at < b.observation_midpoint)
            as events_first_half,
        count(*) filter (where o.created_at >= b.observation_midpoint)
            as events_second_half,
        arg_max(o.repo_name, o.created_at) as primary_repo
    from observation as o
    cross join bounds as b
    group by o.actor_login
    -- Eligibility floor. Drive-by contributors who fire one or two events and
    -- vanish are trivially predictable and, at ~90% of raw rows, they swamp
    -- the signal that matters: whether an *established* contributor lapses.
    -- Applied as HAVING because the predicate is on post-aggregation counts.
    having
        count(*) >= 5
        and count(distinct cast(o.created_at as date)) >= 3

)

select
    f.actor_login,
    f.primary_repo,
    f.first_event_at,
    f.total_events,
    f.distinct_repos,
    f.active_days,
    f.commit_events,
    f.pull_request_events,
    f.issue_events,
    f.comment_events,
    f.engagement_events,
    f.release_events,
    f.weekend_events / cast(f.total_events as double) as weekend_ratio,
    f.total_events / cast(f.active_days as double) as events_per_active_day,
    date_diff('day', f.first_event_at, b.observation_end) as tenure_days,
    -- Anchored to the window edge, never max(created_at), so recency stays
    -- comparable across contributors and avoids target-window leakage.
    date_diff('day', f.last_event_at, b.observation_end)
        as days_since_last_event,
    -- Velocity: share of all observed activity that landed in the final 30
    -- days. Near 0 means the contributor has already gone quiet; near 1 means
    -- they only just arrived. nullif guards the zero-event divide.
    coalesce(
        f.events_last_30_days / nullif(cast(f.total_events as double), 0), 0
    ) as velocity_30d,
    -- Deceleration: raw event delta between the two halves of the window.
    -- Positive means slowing down; negative means ramping up.
    coalesce(f.events_first_half - f.events_second_half, 0)
        as deceleration_score,
    -- Normalised deceleration so the signal is comparable between a maintainer
    -- shedding 400 events and a casual contributor shedding 4.
    coalesce(
        (f.events_first_half - f.events_second_half)
        / nullif(cast(f.total_events as double), 0), 0
    ) as deceleration_ratio,
    -- Binary target, retained so the deployed classifier keeps building while
    -- the survival model is developed alongside it.
    case when t.actor_login is null then 1 else 0 end as is_churned,

    -- Survival targets.
    --
    -- event = 1 when the contributor lapsed (no activity in the target
    -- window), 0 when they were still active at the study cutoff and are
    -- therefore right-censored.
    case when t.actor_login is null then 1 else 0 end as "event",

    -- duration = days under observation from entry until the event or until
    -- censoring, whichever came first.
    --
    --   lapsed    -> first_event_at .. last_event_at (their final activity)
    --   censored  -> first_event_at .. target_end    (the study cutoff)
    --
    -- Censored subjects MUST run to the cutoff, not to their last observed
    -- event. Ending them early would report a shorter survival time than was
    -- actually observed and bias every hazard estimate downward.
    case
        when t.actor_login is null
            then date_diff('day', f.first_event_at, f.last_event_at)
        else date_diff('day', f.first_event_at, b.target_end)
    end as duration
from features as f
cross join bounds as b
left join target as t on f.actor_login = t.actor_login
