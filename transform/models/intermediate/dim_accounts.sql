-- One row per account: team size, lifespan bounds, and current plan.
select
    account_id,
    count(distinct user_id) as team_size,
    min(event_timestamp) as account_created_at,
    max(event_timestamp) as last_active_at,
    arg_max(subscription_plan, event_timestamp) as subscription_plan
from {{ ref('stg_events') }}
group by account_id
