-- Canonical event stream: typed, deduplicated by event_id (latest wins).
select
    event_id,
    event_name,
    event_timestamp::timestamp as event_timestamp,
    user_id,
    account_id,
    session_id,
    device_type,
    platform,
    country,
    region,
    subscription_plan,
    feature_name,
    event_source,
    event_version
from {{ source('raw', 'events') }}
qualify
    row_number() over (partition by event_id order by event_timestamp desc) = 1
