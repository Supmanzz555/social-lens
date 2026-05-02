"""Airflow DAG: ingest streaming — producers → Kafka → Spark streaming.

Producers run as bash commands. Spark streaming uses SparkSubmitOperator.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.providers.apache.spark.operators.spark_submit import SparkSubmitOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=3),
}

dag = DAG(
    "ingest_streaming",
    default_args=default_args,
    description="Poll APIs → push to Kafka → Spark streaming → R2 bronze",
    schedule="*/30 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-pipeline"],
)

producer_hn = BashOperator(
    task_id="produce_hackernews",
    bash_command="python /opt/airflow/producers/hackernews_producer.py --limit 25",
    dag=dag,
)

producer_gh = BashOperator(
    task_id="produce_github",
    bash_command="python /opt/airflow/producers/github_producer.py --limit 25",
    dag=dag,
)

producer_yt = BashOperator(
    task_id="produce_youtube",
    bash_command="python /opt/airflow/producers/youtube_producer.py --limit 10",
    dag=dag,
)

spark_streaming = SparkSubmitOperator(
    task_id="spark_kafka_to_r2",
    application="/opt/airflow/spark/streaming/kafka_to_r2.py",
    conn_id="spark_default",
    name="kafka-to-r2",
    conf={
        "spark.master": "local[*]",
        "spark.driver.memory": "768m",
        "spark.jars.packages": "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.spark:spark-avro_2.12:3.5.1,org.apache.hadoop:hadoop-aws:3.3.4,org.apache.hadoop:hadoop-common:3.3.4",
    },
    retry_delay=timedelta(minutes=3),
    retries=2,
    dag=dag,
)

[producer_hn, producer_gh, producer_yt] >> spark_streaming
