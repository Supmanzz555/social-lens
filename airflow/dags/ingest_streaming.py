"""Airflow DAG: ingest streaming — producers → Kafka → Spark streaming.

Producers run as bash commands. Spark streaming uses SparkSubmitOperator.
Streaming writes to bronze/staging/, commit task moves to bronze/ for batch.
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
    max_active_runs=1,
    tags=["data-pipeline"],
)

producer_hn = BashOperator(
    task_id="produce_hackernews",
    bash_command="KAFKA_BOOTSTRAP_SERVERS_LOCAL=kafka:9092 python /opt/airflow/producers/hackernews_producer.py --limit 25",
    dag=dag,
)

producer_gh = BashOperator(
    task_id="produce_github",
    bash_command="KAFKA_BOOTSTRAP_SERVERS_LOCAL=kafka:9092 python /opt/airflow/producers/github_producer.py --limit 25",
    dag=dag,
)

producer_yt = BashOperator(
    task_id="produce_youtube",
    bash_command="KAFKA_BOOTSTRAP_SERVERS_LOCAL=kafka:9092 python /opt/airflow/producers/youtube_producer.py --limit 10",
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
    env_vars={
        "KAFKA_BOOTSTRAP_SERVERS_LOCAL": "kafka:9092",
    },
    application_args=["--duration", "120"],
    retry_delay=timedelta(minutes=3),
    retries=2,
    dag=dag,
)

commit_bronze = BashOperator(
    task_id="commit_bronze",
    bash_command="""
python -c "
import os, boto3, logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

R2_BUCKET = os.getenv('R2_BUCKET_NAME', 'datalake')
R2_ENDPOINT = f\\\"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com\\\"
s3 = boto3.client('s3', endpoint_url=R2_ENDPOINT,
    aws_access_key_id=os.getenv('R2_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('R2_SECRET_ACCESS_KEY'))

for source in ['hackernews', 'github', 'youtube']:
    staging_prefix = f'bronze/staging/source={source}/'
    final_prefix = f'bronze/source={source}/'
    resp = s3.list_objects_v2(Bucket=R2_BUCKET, Prefix=staging_prefix)
    moved = 0
    for obj in resp.get('Contents', []):
        key = obj['Key']
        if not key.endswith('.parquet'):
            continue
        final_key = key.replace('bronze/staging/', 'bronze/')
        s3.copy_object(Bucket=R2_BUCKET, CopySource={'Bucket': R2_BUCKET, 'Key': key}, Key=final_key)
        s3.delete_object(Bucket=R2_BUCKET, Key=key)
        moved += 1
    logger.info('Moved %d parquet files: %s', moved, source)
"
    """,
    dag=dag,
)

[producer_hn, producer_gh, producer_yt] >> spark_streaming >> commit_bronze
