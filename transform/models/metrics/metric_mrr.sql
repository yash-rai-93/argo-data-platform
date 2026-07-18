-- Monthly recurring revenue, recognised on completed payments.
-- Plan prices are illustrative placeholders (USD/month).
with monthly as (
    select
        date_trunc('month', event_timestamp) as revenue_month,
        sum(case subscription_plan
            when 'Pro' then 20
            when 'Enterprise' then 100
            else 0
        end) as mrr
    from {{ ref('fact_subscriptions') }}
    where subscription_action = 'payment_completed'
    group by date_trunc('month', event_timestamp)
)

select
    revenue_month,
    mrr,
    mrr * 12 as arr
from monthly
order by revenue_month
