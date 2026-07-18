-- Monetization-grain fact: one row per subscription lifecycle action.
select
    event_id,
    event_timestamp,
    user_id,
    account_id,
    event_name as subscription_action,
    subscription_plan
from {{ ref('stg_events') }}
where event_source = 'monetization'
