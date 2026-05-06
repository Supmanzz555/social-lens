select *
from {{ ref('fct_daily_engagement') }}
where avg_score < 0
