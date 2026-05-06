"""PySpark Batch: gold layer → local PostgreSQL.

Reads gold Parquet from R2 and loads into local PostgreSQL (analytics_db).
Creates tables if they don't exist, appends new data.

Usage:
    uv run python spark/batch/gold_to_postgres.py [--date YYYY-MM-DD]
"""

import os
import sys
import argparse
import logging
from datetime import date

from pyspark.sql import SparkSession

# Add project root to path for configs
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from configs.spark_config import get_spark_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

R2_BUCKET = os.getenv("R2_BUCKET_NAME", "datalake")

PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = "5432"
PG_USER = os.getenv("PG_USER", "airflow")
PG_PASSWORD = os.getenv("PG_PASSWORD", "airflow")
PG_DB = "analytics_db"

PG_URL = f"jdbc:postgresql://{PG_HOST}:{PG_PORT}/{PG_DB}"
PG_PROPS = {
    "user": PG_USER,
    "password": PG_PASSWORD,
    "driver": "org.postgresql.Driver",
}

TABLES = {
    "content_engagement": "gold_content_engagement",
    "creator_metrics": "gold_creator_metrics",
    "trending_topics": "gold_trending_topics",
    "individual_items": "gold_individual_items",
}


def read_gold(spark, table):
    """Read a gold Parquet table."""
    path = f"s3a://{R2_BUCKET}/gold/{table}/"
    try:
        df = spark.read.parquet(path)
        rows = df.count()
        logger.info("Read %d rows from gold/%s", rows, table)
        return df if rows > 0 else None
    except Exception as e:
        logger.warning("No gold data for %s: %s", table, e)
        return None


def load_to_postgres(df, pg_table):
    """Write DataFrame to PostgreSQL, replacing existing data."""
    import psycopg2

    conn = psycopg2.connect(host=PG_HOST, port=PG_PORT, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)
    cur = conn.cursor()
    try:
        cur.execute(f"DELETE FROM {pg_table}")
        conn.commit()
        logger.info("Cleared existing data from %s", pg_table)
        mode = "append"
    except Exception:
        conn.rollback()
        logger.info("Table %s does not exist, will create it", pg_table)
        mode = "overwrite"

    (
        df.write
        .format("jdbc")
        .option("url", PG_URL)
        .option("dbtable", pg_table)
        .options(**PG_PROPS)
        .mode(mode)
        .save()
    )
    conn.close()
    logger.info("Loaded %d rows → %s (mode=%s)", df.count(), pg_table, mode)


def run(partition_date=None):
    """Run gold → PostgreSQL load."""
    if partition_date is None:
        partition_date = date.today().isoformat()

    logger.info("Starting gold → PostgreSQL for date=%s", partition_date)

    spark = (
        SparkSession.builder
        .appName("gold-to-postgres")
        .config("spark.jars.packages", "org.postgresql:postgresql:42.7.3,org.apache.hadoop:hadoop-aws:3.3.4,org.apache.hadoop:hadoop-common:3.3.4")
        .config("spark.hadoop.fs.s3a.endpoint", f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com")
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("R2_ACCESS_KEY_ID"))
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("R2_SECRET_ACCESS_KEY"))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "true")
        .config("spark.driver.memory", "512m")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    errors = []
    for gold_table, pg_table in TABLES.items():
        df = read_gold(spark, gold_table)
        if df is not None:
            try:
                load_to_postgres(df, pg_table)
            except Exception as e:
                logger.error("Failed to load %s: %s", gold_table, e)
                errors.append(f"{gold_table}: {e}")

    spark.stop()
    if errors:
        logger.error("Failed to load %d table(s) to PostgreSQL: %s", len(errors), "; ".join(errors))
        sys.exit(1)
    logger.info("Done. Gold data loaded to local PostgreSQL.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None, help="Partition date (YYYY-MM-DD)")
    args = parser.parse_args()
    run(partition_date=args.date)
