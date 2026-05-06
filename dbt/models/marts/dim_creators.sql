with creator_data as (
    select * from {{ source('gold_layer', 'gold_creator_metrics') }}
),
renamed as (
    select
        cast(date as date) as date,
        creator,
        source as platform,
        post_count,
        avg_score,
        max_score,
        total_comments,
        event_count,
        event_types,
        video_count,
        avg_views,
        total_views,
        avg_likes
    from creator_data
)
select * from renamed
