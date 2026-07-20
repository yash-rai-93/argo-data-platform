{{ config(materialized='table') }}

-- Triangular cohort retention.
--
-- Cohort = the calendar month a contributor's first observed event lands in.
-- Period offset = whole months elapsed since that cohort month. A cell exists
-- only where at least one contributor from that cohort was actually active in
-- that period, so the grid is naturally triangular: an August cohort has no
-- observable offset 5 inside a window that ends in December.
--
-- Zero-filling the empty upper-right is the classic error here. It reports
-- "0% retained" for periods that were never observed at all, which drags every
-- recent cohort's curve to the floor and makes the platform look like it is
-- collapsing. Absent means unobserved, not churned. The frontend renders the
-- gap; it does not paint it red.
--
-- Columnar notes: the source is scanned exactly once into `contributor_months`
-- at (actor, month) grain, which collapses 547k event rows to a few tens of
-- thousands before any join. Every downstream CTE reads that reduced relation.

with bounds as (

    -- The extract ends on a partial month. Including it would show every
    -- cohort falling off a cliff in the final column.
    select date_trunc('month', max(created_at)) as incomplete_month
    from {{ source('github_archive', 'raw_github_events') }}

),

contributor_months as (

    select distinct
        actor_login,
        date_trunc('month', created_at) as activity_month
    from {{ source('github_archive', 'raw_github_events') }}
    cross join bounds as b
    where created_at < b.incomplete_month

),

cohorts as (

    select
        actor_login,
        min(activity_month) as cohort_month
    from contributor_months
    group by actor_login

),

cohort_sizes as (

    select
        cohort_month,
        count(*) as cohort_size
    from cohorts
    group by cohort_month

),

activity as (

    select
        c.cohort_month,
        date_diff('month', c.cohort_month, m.activity_month) as period_offset,
        count(*) as retained_contributors
    from contributor_months as m
    inner join cohorts as c
        on m.actor_login = c.actor_login
    group by c.cohort_month, date_diff('month', c.cohort_month, m.activity_month)

)

select
    a.cohort_month,
    strftime(a.cohort_month, '%b %Y') as cohort_label,
    a.period_offset,
    s.cohort_size,
    a.retained_contributors,
    a.retained_contributors / cast(s.cohort_size as double) as retention_rate
from activity as a
inner join cohort_sizes as s
    on a.cohort_month = s.cohort_month
order by a.cohort_month asc, a.period_offset asc
