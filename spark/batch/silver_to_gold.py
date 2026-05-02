"""PySpark Batch: silver → gold layer.

Reads cleaned silver Parquet from all 3 sources, aggregates into
business-ready gold tables, and writes to R2 gold/.

Produces:
- gold/content_engagement/ — daily engagement metrics per source
- gold/creator_metrics/ — per-creator stats across platforms
- gold/trending_topics/ — top topics, tags, and trending keywords

Usage:
    uv run python spark/batch/silver_to_gold.py [--date YYYY-MM-DD]
"""

import os
import sys
import argparse
import logging
from datetime import date

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, sum, avg, max, min, lit, explode, split, regexp_replace,
    lower, length, substring_index, desc, coalesce, array, countDistinct
)

# Add project root to path for configs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from configs.spark_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

R2_BUCKET = os.getenv("R2_BUCKET_NAME", "datalake")


def read_silver(spark, source):
    """Read all silver Parquet for a source."""
    path = f"s3a://{R2_BUCKET}/silver/{source}/"
    try:
        df = spark.read.parquet(path)
        row_count = df.count()
        logger.info("Read %d rows from silver %s", row_count, source)
        return df
    except Exception:
        logger.warning("No silver data for %s", source)
        return None


def build_content_engagement(hn, gh, yt, partition_date):
    """Unified daily engagement metrics per source."""
    frames = []

    if hn is not None and hn.count() > 0:
        hn_agg = (
            hn
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("hackernews"))
            .groupBy("date", "source")
            .agg(
                count("*").alias("total_items"),
                avg("score").alias("avg_score"),
                max("score").alias("max_score"),
                avg("descendants").alias("avg_comments"),
                count("url").alias("items_with_url"),
            )
        )
        frames.append(hn_agg)

    if gh is not None and gh.count() > 0:
        gh_agg = (
            gh
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("github"))
            .groupBy("date", "source", "type")
            .agg(
                count("*").alias("total_items"),
                count("actor_login").alias("unique_actors"),
            )
        )
        frames.append(gh_agg)

    if yt is not None and yt.count() > 0:
        yt_agg = (
            yt
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("youtube"))
            .groupBy("date", "source")
            .agg(
                count("*").alias("total_items"),
                avg("view_count").alias("avg_views"),
                max("view_count").alias("max_views"),
                avg("like_count").alias("avg_likes"),
                avg("comment_count").alias("avg_comments"),
                avg("duration_seconds").alias("avg_duration"),
            )
        )
        frames.append(yt_agg)

    if frames:
        combined = frames[0]
        for f in frames[1:]:
            combined = combined.unionByName(f, allowMissingColumns=True)
        logger.info("Content engagement: %d rows", combined.count())
        return combined

    return None


def build_creator_metrics(hn, gh, yt, partition_date):
    """Per-creator stats across platforms."""
    frames = []

    if hn is not None and hn.count() > 0:
        hn_creators = (
            hn.filter(col("by") != "")
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("hackernews"))
            .withColumn("creator", col("by"))
            .groupBy("date", "source", "creator")
            .agg(
                count("*").alias("post_count"),
                avg("score").alias("avg_score"),
                max("score").alias("max_score"),
                sum("descendants").alias("total_comments"),
            )
        )
        frames.append(hn_creators)

    if gh is not None and gh.count() > 0:
        gh_creators = (
            gh.filter(col("actor_login").isNotNull() & (col("actor_login") != ""))
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("github"))
            .withColumn("creator", col("actor_login"))
            .groupBy("date", "source", "creator")
            .agg(
                count("*").alias("event_count"),
                countDistinct("type").alias("event_types"),
            )
        )
        frames.append(gh_creators)

    if yt is not None and yt.count() > 0:
        yt_creators = (
            yt.filter(col("channel") != "")
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("youtube"))
            .withColumn("creator", col("channel"))
            .groupBy("date", "source", "creator")
            .agg(
                count("*").alias("video_count"),
                avg("view_count").alias("avg_views"),
                sum("view_count").alias("total_views"),
                avg("like_count").alias("avg_likes"),
            )
        )
        frames.append(yt_creators)

    if frames:
        combined = frames[0]
        for f in frames[1:]:
            combined = combined.unionByName(f, allowMissingColumns=True)
        logger.info("Creator metrics: %d rows", combined.count())
        return combined

    return None


def build_trending_topics(hn, gh, yt, partition_date):
    """Top topics, tags, and keywords."""
    frames = []

    if hn is not None and hn.count() > 0:
        # Extract top words from HN titles
        hn_words = (
            hn.filter(length(col("title")) > 3)
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("hackernews"))
            .withColumn("word", explode(split(lower(col("title")), "\\s+")))
            .filter(length(col("word")) > 3)
            .groupBy("date", "source", "word")
            .agg(
                count("*").alias("frequency"),
                avg("score").alias("avg_score"),
            )
            .orderBy(desc("frequency"))
            .limit(50)
        )
        frames.append(hn_words)

    if yt is not None and yt.count() > 0:
        # Use YouTube tags (already exploded by bronze_to_silver)
        yt_tags = (
            yt.filter((col("tag").isNotNull()) & (col("tag") != ""))
            .withColumn("date", lit(partition_date))
            .withColumn("source", lit("youtube"))
            .groupBy("date", "source", "tag")
            .agg(
                count("*").alias("frequency"),
                avg("view_count").alias("avg_views"),
            )
            .orderBy(desc("frequency"))
            .limit(50)
        )
        frames.append(yt_tags)

    if frames:
        combined = frames[0]
        for f in frames[1:]:
            combined = combined.unionByName(f, allowMissingColumns=True)
        logger.info("Trending topics: %d rows", combined.count())
        return combined

    return None


def run(partition_date=None):
    """Run silver → gold transformation."""
    if partition_date is None:
        partition_date = date.today().isoformat()

    logger.info("Starting silver → gold for date=%s", partition_date)

    spark = get_spark_session("silver-to-gold")

    # Read all silver data
    hn = read_silver(spark, "hackernews")
    gh = read_silver(spark, "github")
    yt = read_silver(spark, "youtube")

    # Build gold tables
    engagement = build_content_engagement(hn, gh, yt, partition_date)
    if engagement is not None:
        engagement.write.mode("overwrite").parquet(
            f"s3a://{R2_BUCKET}/gold/content_engagement/"
        )
        logger.info("Wrote gold/content_engagement")

    creators = build_creator_metrics(hn, gh, yt, partition_date)
    if creators is not None:
        creators.write.mode("overwrite").parquet(
            f"s3a://{R2_BUCKET}/gold/creator_metrics/"
        )
        logger.info("Wrote gold/creator_metrics")

    topics = build_trending_topics(hn, gh, yt, partition_date)
    if topics is not None:
        topics.write.mode("overwrite").parquet(
            f"s3a://{R2_BUCKET}/gold/trending_topics/"
        )
        logger.info("Wrote gold/trending_topics")

    spark.stop()
    logger.info("Done. Gold layer ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="Partition date (YYYY-MM-DD)")
    args = parser.parse_args()
    run(partition_date=args.date)
