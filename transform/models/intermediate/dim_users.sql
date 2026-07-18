-- One row per user: lifespan bounds plus their most recent attributes.
select
    user_id,
    country,
    region,
    device_type,
    platform,
    subscription_plan,
    min(event_timestamp) over (partition by user_id) as first_seen_at,
    max(event_timestamp) over (partition by user_id) as last_seen_at
from {{ ref('stg_events') }}
qualify
    row_number() over (partition by user_id order by event_timestamp desc) = 1
