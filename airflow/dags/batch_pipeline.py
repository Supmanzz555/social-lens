"""Airflow DAG: batch pipeline — bronze → silver → gold → PostgreSQL.

Uses SparkSubmitOperator to submit PySpark jobs in local mode.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "batch_pipeline",
    default_args=default_args,
    description="Batch transformation: bronze → silver → gold → PostgreSQL",
    schedule="0 2 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-pipeline"],
)

SPARK_HOME = "/home/airflow/.local/lib/python3.11/site-packages/pyspark/jars"

bronze_to_silver = SparkSubmitOperator(
    task_id="bronze_to_silver",
    application="/opt/airflow/spark/batch/bronze_to_silver.py",
    conn_id="spark_default",
    name="bronze-to-silver",
    conf={
        "spark.master": "local[*]",
        "spark.driver.memory": "512m",
    },
    retry_delay=timedelta(minutes=5),
    dag=dag,
)

silver_to_gold = SparkSubmitOperator(
    task_id="silver_to_gold",
    application="/opt/airflow/spark/batch/silver_to_gold.py",
    conn_id="spark_default",
    name="silver-to-gold",
    conf={
        "spark.master": "local[*]",
        "spark.driver.memory": "512m",
    },
    retry_delay=timedelta(minutes=5),
    dag=dag,
)

gold_to_postgres = SparkSubmitOperator(
    task_id="gold_to_postgres",
    application="/opt/airflow/spark/batch/gold_to_postgres.py",
    conn_id="spark_default",
    name="gold-to-postgres",
    conf={
        "spark.master": "local[*]",
        "spark.driver.memory": "512m",
    },
    retry_delay=timedelta(minutes=5),
    dag=dag,
)

[bronze_to_silver >> silver_to_gold >> gold_to_postgres]
