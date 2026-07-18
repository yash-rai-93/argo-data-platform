-- One row per session: time bounds, duration, and event volume.
select
    session_id,
    user_id,
    account_id,
    min(event_timestamp) as session_start_at,
    max(event_timestamp) as session_end_at,
    date_diff('second', min(event_timestamp), max(event_timestamp))
        as duration_seconds,
    count(event_id) as event_count
from {{ ref('stg_events') }}
where session_id is not null
group by session_id, user_id, account_id
