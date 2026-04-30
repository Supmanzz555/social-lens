"""PySpark Structured Streaming: Kafka → R2 bronze layer.

Reads from 3 Kafka topics simultaneously and writes partitioned Parquet files
to Cloudflare R2 in bronze/source=X/date=Y/ structure.

Usage:
    uv run python spark/streaming/kafka_to_r2.py [--duration SECONDS]

By default runs until Ctrl+C. Use --duration to auto-stop after N seconds.
"""

import os
import sys
import argparse
import logging
from datetime import datetime

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, current_date, to_date, from_unixtime,
    lit, current_timestamp,
)
from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, LongType, ArrayType
)

# Add project root to path for configs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from configs.spark_config import get_spark_with_kafka

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS_LOCAL", "localhost:9092")
R2_BUCKET = os.getenv("R2_BUCKET_NAME", "datalake")

TOPICS = {
    "hackernews-posts": "hackernews",
    "github-events": "github",
    "youtube-videos": "youtube",
}

HN_SCHEMA = StructType([
    StructField("id", IntegerType(), True),
    StructField("title", StringType(), True),
    StructField("type", StringType(), True),
    StructField("by", StringType(), True),
    StructField("score", IntegerType(), True),
    StructField("descendants", IntegerType(), True),
    StructField("time", LongType(), True),
    StructField("url", StringType(), True),
    StructField("text", StringType(), True),
])

GH_SCHEMA = StructType([
    StructField("id", StringType(), True),
    StructField("type", StringType(), True),
    StructField("actor", StructType([
        StructField("id", LongType(), True),
        StructField("login", StringType(), True),
    ]), True),
    StructField("repo", StringType(), True),
    StructField("created_at", StringType(), True),
    StructField("payload", StringType(), True),
    StructField("public", StringType(), True),
])

YT_SCHEMA = StructType([
    StructField("video_id", StringType(), True),
    StructField("title", StringType(), True),
    StructField("channel", StringType(), True),
    StructField("channel_id", StringType(), True),
    StructField("published_at", StringType(), True),
    StructField("description", StringType(), True),
    StructField("tags", ArrayType(StringType()), True),
    StructField("category_id", StringType(), True),
    StructField("view_count", IntegerType(), True),
    StructField("like_count", IntegerType(), True),
    StructField("comment_count", IntegerType(), True),
    StructField("duration_seconds", IntegerType(), True),
])


def read_kafka_topic(spark, topic):
    """Create a streaming DataFrame from a single Kafka topic."""
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", BOOTSTRAP)
        .option("subscribe", topic)
        .option("startingOffsets", "earliest")
        .option("failOnDataLoss", "false")
        .load()
        .selectExpr("CAST(value AS STRING) as raw_json")
    )


def build_write_stream(df, source_name):
    """Build and return a streaming write query for a source."""
    parsed = df.select(
        from_json(col("raw_json"), HN_SCHEMA if source_name == "hackernews"
                  else GH_SCHEMA if source_name == "github"
                  else YT_SCHEMA).alias("data"),
    ).select("data.*")

    enriched = parsed.withColumn(
        "source", lit(source_name)
    ).withColumn(
        "ingested_at", current_timestamp()
    ).withColumn(
        "partition_date", current_date()
    )

    checkpoint_dir = f"spark/streaming/checkpoints/{source_name}"
    r2_path = f"s3a://{R2_BUCKET}/bronze/source={source_name}"

    query = (
        enriched.writeStream
        .format("parquet")
        .option("path", r2_path)
        .option("checkpointLocation", checkpoint_dir)
        .option("mergeSchema", "true")
        .outputMode("append")
        .trigger(processingTime="10 seconds")
        .start()
    )

    logger.info("Started streaming %s → %s", source_name, r2_path)
    return query


def run(duration=None):
    """Run the Kafka-to-R2 streaming job."""
    logger.info("Starting Kafka → R2 streaming job")
    logger.info("Kafka bootstrap: %s", BOOTSTRAP)
    logger.info("R2 bucket: %s", R2_BUCKET)

    spark = get_spark_with_kafka("kafka-to-r2-streaming")

    queries = []
    for topic, source_name in TOPICS.items():
        df = read_kafka_topic(spark, topic)
        q = build_write_stream(df, source_name)
        queries.append(q)

    try:
        if duration:
            logger.info("Running for %d seconds then stopping...", duration)
            spark.streams.awaitAnyTermination(duration)
            for q in queries:
                q.stop()
            logger.info("Stopped all streaming queries after %d seconds", duration)
        else:
            logger.info("Running until Ctrl+C...")
            spark.streams.awaitAnyTermination()
    except KeyboardInterrupt:
        logger.info("Interrupted. Stopping queries...")
        for q in queries:
            q.stop()

    spark.stop()
    logger.info("Spark session stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=None,
                        help="Run for N seconds then stop")
    args = parser.parse_args()
    run(duration=args.duration)
