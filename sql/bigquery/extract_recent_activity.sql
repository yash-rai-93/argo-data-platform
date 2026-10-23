-- Manual refresh: concrete daily tables are rendered from validated dates.
-- Match the historical cohort scope, without reading its training warehouse.
with python_repos as (
    select repo
    from unnest([
        'python/cpython',
        'django/django',
        'pallets/flask',
        'pandas-dev/pandas',
        'numpy/numpy',
        'scipy/scipy',
        'scikit-learn/scikit-learn',
        'pytorch/pytorch',
        'huggingface/transformers',
        'tiangolo/fastapi',
        'fastapi/fastapi', -- Current name; keep the old name for archive continuity.
        'encode/django-rest-framework',
        'psf/requests',
        'pypa/pip',
        'apache/airflow',
        'ansible/ansible',
        'scrapy/scrapy',
        'celery/celery',
        'sqlalchemy/sqlalchemy',
        'matplotlib/matplotlib',
        'keras-team/keras',
        'streamlit/streamlit',
        'pydantic/pydantic',
        'pytest-dev/pytest',
        'jupyterlab/jupyterlab'
    ]) as repo
),

scoped as (
    select
        id as event_id,
        type as event_type,
        actor.login as actor_login,
        repo.name as repo_name,
        created_at
    from (
        __DAILY_TABLES__
    )
    where created_at >= timestamp('__START__')
        and created_at < timestamp('__END__')
        and type in (
            'PushEvent',
            'PullRequestEvent',
            'PullRequestReviewEvent',
            'PullRequestReviewCommentEvent',
            'IssuesEvent',
            'IssueCommentEvent',
            'CommitCommentEvent',
            'CreateEvent',
            'ForkEvent',
            'WatchEvent',
            'ReleaseEvent'
        )
)

select
    s.event_id,
    s.event_type,
    -- Collapse raw event types into behavioural categories used as features.
    case
        when s.event_type = 'PushEvent' then 'commit'
        when s.event_type like 'PullRequest%' then 'pull_request'
        when s.event_type like 'Issue%' then 'issue'
        when s.event_type = 'CommitCommentEvent' then 'comment'
        when s.event_type in ('ForkEvent', 'WatchEvent') then 'engagement'
        when s.event_type in ('CreateEvent', 'ReleaseEvent') then 'release'
        else 'other'
    end as event_category,
    s.actor_login,
    s.repo_name,
    s.created_at
from scoped as s
inner join python_repos as p
    on s.repo_name = p.repo
-- Drop automation/bot accounts so the cohort is real humans.
where s.actor_login not like '%[bot]%'
    and s.actor_login not in (
        'dependabot',
        'dependabot-preview',
        'github-actions',
        'renovate',
        'renovate-bot',
        'codecov',
        'stale',
        'mergify',
        'pre-commit-ci'
    );
