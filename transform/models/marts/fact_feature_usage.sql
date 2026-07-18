-- Feature-grain fact: events that touched a named feature.
select
    event_id,
    event_timestamp,
    user_id,
    account_id,
    session_id,
    feature_name,
    event_name
from {{ ref('stg_events') }}
where feature_name is not null
