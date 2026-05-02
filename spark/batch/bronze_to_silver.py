"""PySpark Batch: bronze → silver layer.

Reads raw Parquet from R2 bronze/, cleans and deduplicates each source,
then writes to R2 silver/ in partitioned format.

Usage:
    uv run python spark/batch/bronze_to_silver.py [--date YYYY-MM-DD]

If no date given, processes today's data.
"""

import os
import sys
import argparse
import logging
from datetime import datetime, date

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, to_timestamp, from_unixtime, coalesce, lit, lower, trim,
    length, regexp_replace, explode, row_number, desc
)
from pyspark.sql.window import Window

# Add project root to path for configs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from configs.spark_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

R2_BUCKET = os.getenv("R2_BUCKET_NAME", "datalake")


def read_bronze(spark, source):
    """Read all bronze Parquet for a source."""
    path = f"s3a://{R2_BUCKET}/bronze/source={source}/"
    df = spark.read.parquet(path)
    row_count = df.count()
    logger.info("Read %d rows from bronze %s", row_count, source)
    return df


def clean_hackernews(df):
    """Clean and deduplicate Hacker News data."""
    cleaned = (
        df
        # Drop rows with null id (can't dedup without it)
        .filter(col("id").isNotNull())
        # Normalize text fields
        .withColumn("title", coalesce(trim(col("title")), lit("")))
        .withColumn("text", coalesce(trim(col("text")), lit("")))
        .withColumn("by", coalesce(trim(col("by")), lit("")))
        .withColumn("url", coalesce(trim(col("url")), lit("")))
        # Convert Unix timestamp to proper timestamp
        .withColumn("created_at", from_unixtime(col("time")))
        # Drop raw Unix time and partition metadata columns
        .drop("time", "partition_date", "ingested_at")
        # Deduplicate by id (keep latest)
        .withColumn("_rn", row_number().over(Window.partitionBy("id").orderBy(desc("score"))))
        .filter(col("_rn") == 1)
        .drop("_rn")
    )
    logger.info("HackerNews: %d raw → %d clean rows", df.count(), cleaned.count())
    return cleaned


def clean_github(df):
    """Clean and deduplicate GitHub data."""
    cleaned = (
        df
        .filter(col("id").isNotNull())
        # Flatten the actor struct into separate columns
        .withColumn("actor_id", col("actor.id"))
        .withColumn("actor_login", col("actor.login"))
        # Normalize repo
        .withColumn("repo", coalesce(trim(col("repo")), lit("")))
        # Parse created_at to timestamp
        .withColumn("created_at", to_timestamp(col("created_at")))
        # Ensure payload is string (sometimes comes as JSON string)
        .withColumn("payload", coalesce(col("payload"), lit("")))
        # Drop raw struct and metadata
        .drop("actor", "partition_date", "ingested_at")
        # Deduplicate by id
        .withColumn("_rn", row_number().over(Window.partitionBy("id").orderBy(desc("created_at"))))
        .filter(col("_rn") == 1)
        .drop("_rn")
    )
    logger.info("GitHub: %d raw → %d clean rows", df.count(), cleaned.count())
    return cleaned


def clean_youtube(df):
    """Clean and deduplicate YouTube data."""
    cleaned = (
        df
        .filter(col("video_id").isNotNull())
        # Normalize text
        .withColumn("title", coalesce(trim(col("title")), lit("")))
        .withColumn("description", coalesce(trim(col("description")), lit("")))
        .withColumn("channel", coalesce(trim(col("channel")), lit("")))
        # Parse published_at to timestamp
        .withColumn("published_at_ts", to_timestamp(col("published_at")))
        # Ensure numeric fields are valid
        .withColumn("view_count", coalesce(col("view_count"), lit(0)))
        .withColumn("like_count", coalesce(col("like_count"), lit(0)))
        .withColumn("comment_count", coalesce(col("comment_count"), lit(0)))
        .withColumn("duration_seconds", coalesce(col("duration_seconds"), lit(0)))
        # Explode tags for flat representation (keep both original and exploded)
        .withColumn("tag", explode(coalesce(col("tags"), lit([]))))
        # Drop raw list and metadata
        .drop("tags", "partition_date", "ingested_at", "published_at")
        # Deduplicate by video_id
        .withColumn("_rn", row_number().over(Window.partitionBy("video_id").orderBy(desc("view_count"))))
        .filter(col("_rn") == 1)
        .drop("_rn")
    )
    logger.info("YouTube: %d raw → %d clean rows", df.count(), cleaned.count())
    return cleaned


def run(partition_date=None):
    """Run bronze → silver transformation."""
    if partition_date is None:
        partition_date = date.today().isoformat()

    logger.info("Starting bronze → silver for date=%s", partition_date)

    spark = get_spark_session("bronze-to-silver")

    sources = {
        "hackernews": clean_hackernews,
        "github": clean_github,
        "youtube": clean_youtube,
    }

    for source, cleaner in sources.items():
        try:
            df = read_bronze(spark, source)
            if df.count() == 0:
                logger.warning("No bronze data for %s, skipping", source)
                continue

            cleaned = cleaner(df)
            out_path = f"s3a://{R2_BUCKET}/silver/{source}/"
            cleaned.write.mode("overwrite").parquet(out_path)
            logger.info("Wrote silver data for %s → %s", source, out_path)
        except Exception as e:
            logger.error("Failed to process %s: %s", source, e)

    spark.stop()
    logger.info("Done. Silver layer ready.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="Partition date (YYYY-MM-DD)")
    args = parser.parse_args()
    run(partition_date=args.date)
