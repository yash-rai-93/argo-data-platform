-- Project Argo -- real-data extraction (BigQuery Standard SQL)
--
-- Source:  githubarchive public dataset (every public GitHub event since 2011).
-- Purpose: pull cleaned, scoped events for open-source *contributor churn*
--          modelling across the top Python open-source projects.
--
-- Cost control (why this query is cheap despite a huge source):
--   * `_TABLE_SUFFIX` prunes the day-partitioned wildcard so BigQuery only
--     scans the chosen date window, not the whole 2011->today history.
--   * Only five small columns are read. The large `payload` JSON is never
--     touched, which is what keeps bytes-scanned (and cost) low.
--   * A curated repo allow-list keeps the cohort focused and defensible.
--
-- Before running: click "More > Query settings" in the BigQuery console (or
-- use `bq query --dry_run`) to preview estimated bytes scanned.

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
    from `githubarchive.day.*`
    -- Change these two YYYYMMDD dates to move the analysis window.
    where _table_suffix between '20230701' and '20231231'
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
