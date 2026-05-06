"""Airflow DAG: ML pipeline for weekly HN score prediction model training.

Tasks:
  1. generate_synthetic_data — runs ml/generate_synthetic.py
  2. train_model — runs ml/train_model.py (logs to MLflow, registers best)
  3. predict — runs ml/predict.py (scores new posts, writes to Postgres)

Schedule: Weekly on Sunday at 3 AM.
"""

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

ml_env = {
    **os.environ,
    "PYTHONPATH": "/opt/airflow",
    "MLFLOW_TRACKING_URI": "http://mlflow:5000",
}

with DAG(
    "ml_pipeline",
    default_args=default_args,
    description="ML model training and prediction pipeline",
    schedule="0 3 * * 0",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["ml", "mlflow", "hackernews"],
) as dag:

    generate = BashOperator(
        task_id="generate_synthetic_data",
        bash_command="cd /opt/airflow && python ml/generate_synthetic.py --n 1000",
        env=ml_env,
    )

    train = BashOperator(
        task_id="train_model",
        bash_command="cd /opt/airflow && python ml/train_model.py",
        env=ml_env,
    )

    predict = BashOperator(
        task_id="predict",
        bash_command="cd /opt/airflow && python ml/predict.py --n 100",
        env={
            **ml_env,
            "PG_HOST": "postgres",
        },
    )

    generate >> train >> predict
