"""
Spark session configuration for local PySpark jobs.

Configures:
- Cloudflare R2 as S3-compatible storage
- Memory settings for local execution
- Kafka package for streaming jobs
"""

from pyspark.sql import SparkSession
import os
from dotenv import load_dotenv

load_dotenv()


def get_spark_session(app_name: str = "social-media-pipeline") -> SparkSession:
    """Create a SparkSession configured for R2 and Kafka."""

    r2_account_id = os.getenv("R2_ACCOUNT_ID")
    r2_access_key = os.getenv("R2_ACCESS_KEY_ID")
    r2_secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

    spark = (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.jars.packages",
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "org.apache.hadoop:hadoop-common:3.3.4",
        )
        .config("spark.hadoop.fs.s3a.endpoint", f"https://{r2_account_id}.r2.cloudflarestorage.com")
        .config("spark.hadoop.fs.s3a.access.key", r2_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", r2_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "true")
        .config("spark.sql.streaming.schemaInference", "true")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "512m")
        .config("spark.executor.memory", "512m")
        .config("spark.sql.shuffle.partitions", "4")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    return spark


def get_spark_with_kafka(app_name: str = "social-media-streaming") -> SparkSession:
    """Create a SparkSession with Kafka packages included."""

    r2_account_id = os.getenv("R2_ACCOUNT_ID")
    r2_access_key = os.getenv("R2_ACCESS_KEY_ID")
    r2_secret_key = os.getenv("R2_SECRET_ACCESS_KEY")

    spark = (
        SparkSession.builder.appName(app_name)
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,"
            "org.apache.spark:spark-avro_2.12:3.5.1,"
            "org.apache.hadoop:hadoop-aws:3.3.4,"
            "org.apache.hadoop:hadoop-common:3.3.4",
        )
        .config("spark.hadoop.fs.s3a.endpoint", f"https://{r2_account_id}.r2.cloudflarestorage.com")
        .config("spark.hadoop.fs.s3a.access.key", r2_access_key)
        .config("spark.hadoop.fs.s3a.secret.key", r2_secret_key)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "true")
        .config("spark.sql.streaming.schemaInference", "true")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.driver.memory", "768m")
        .config("spark.executor.memory", "768m")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    return spark
