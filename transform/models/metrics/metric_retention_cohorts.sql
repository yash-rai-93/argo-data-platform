-- N-day retention by signup-day cohort.
select
    date_trunc('day', u.first_seen_at) as cohort_date,
    count(distinct u.user_id) as cohort_size,
    count(distinct case
        when date_diff('day', u.first_seen_at, s.session_start_at) = 1
            then s.user_id
    end) as day_1_retained,
    count(distinct case
        when date_diff('day', u.first_seen_at, s.session_start_at) = 7
            then s.user_id
    end) as day_7_retained,
    count(distinct case
        when date_diff('day', u.first_seen_at, s.session_start_at) = 30
            then s.user_id
    end) as day_30_retained
from {{ ref('dim_users') }} as u
inner join {{ ref('fact_sessions') }} as s on u.user_id = s.user_id
group by date_trunc('day', u.first_seen_at)
order by cohort_date
