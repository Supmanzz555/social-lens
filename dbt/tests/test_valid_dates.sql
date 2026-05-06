select *
from {{ ref('fct_daily_engagement') }}
where date < '2020-01-01' or date > current_date
