with source as (
    select * from {{ source('gold_layer', 'gold_content_engagement') }}
    where source = 'github'
),
renamed as (
    select
        cast(date as date) as date,
        'github' as platform,
        type,
        total_items,
        avg_score,
        max_score,
        avg_comments,
        items_with_url,
        unique_actors,
        cast(null as double precision) as avg_views,
        cast(null as integer) as max_views,
        cast(null as double precision) as avg_likes,
        cast(null as double precision) as avg_duration
    from source
)
select * from renamed
