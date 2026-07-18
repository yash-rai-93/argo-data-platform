-- Event-grain fact: the analytic spine for product behaviour.
select
    event_id,
    event_name,
    event_timestamp,
    user_id,
    account_id,
    session_id,
    feature_name,
    event_source
from {{ ref('stg_events') }}
