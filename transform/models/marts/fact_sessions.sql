-- Session-grain fact, enriched with the user's current attributes.
select
    s.session_id,
    s.user_id,
    s.account_id,
    s.session_start_at,
    s.session_end_at,
    s.duration_seconds,
    s.event_count,
    u.subscription_plan,
    u.platform,
    u.device_type
from {{ ref('int_sessions') }} as s
inner join {{ ref('dim_users') }} as u on s.user_id = u.user_id
