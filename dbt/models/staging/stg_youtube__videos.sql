with source as (
    select * from {{ source('gold_layer', 'gold_content_engagement') }}
    where source = 'youtube'
),
renamed as (
    select
        cast(date as date) as date,
        'youtube' as platform,
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
    from source
)
select * from renamed
