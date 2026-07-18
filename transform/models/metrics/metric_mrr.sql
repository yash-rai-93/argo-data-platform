-- Monthly recurring revenue, priced from the subscription-plan seed.
with monthly as (
    select
        date_trunc('month', f.event_timestamp) as revenue_month,
        sum(p.monthly_price) as mrr
    from {{ ref('fact_subscriptions') }} as f
    inner join {{ ref('dim_subscription_plan') }} as p
        on f.subscription_plan = p.subscription_plan
    where f.subscription_action = 'payment_completed'
    group by date_trunc('month', f.event_timestamp)
)

select
    revenue_month,
    mrr,
    mrr * 12 as arr
from monthly
order by revenue_month
