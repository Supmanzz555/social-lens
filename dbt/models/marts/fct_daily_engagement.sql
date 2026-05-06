with daily_metrics as (
    select * from {{ ref('int_daily_metrics') }}
)
select
    date,
    platform,
    type,
    total_items,
    avg_score,
    max_score,
    avg_comments,
    items_with_url,
    unique_actors,
    avg_views,
    max_views,
    avg_likes,
    avg_duration
from daily_metrics
