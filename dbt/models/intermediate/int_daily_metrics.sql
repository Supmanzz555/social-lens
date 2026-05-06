with combined as (
    select * from {{ ref('stg_hackernews__stories') }}
    union all
    select * from {{ ref('stg_github__events') }}
    union all
    select * from {{ ref('stg_youtube__videos') }}
)
select * from combined
