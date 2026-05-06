"""Airflow DAG: data quality — Great Expectations validation.

Validates silver data after bronze→silver transformation.
Runs expectation suites for all 3 sources.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "data_quality",
    default_args=default_args,
    description="Great Expectations validation of silver data",
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-pipeline", "data-quality"],
)

validate_quality = BashOperator(
    task_id="validate_silver_quality",
    bash_command="cd /opt/airflow && python scripts/run_data_quality.py",
    retries=1,
    dag=dag,
)
