"""Airflow DAG: data quality — Great Expectations validation.

Validates data at layer transitions:
1. bronze → silver validation
2. silver → gold validation

Schedule: runs after batch_pipeline (external dependency).
Currently a placeholder — Great Expectations will be implemented in Phase 6.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator

default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "data_quality",
    default_args=default_args,
    description="Great Expectations validation at layer transitions",
    schedule=None,  # Triggered manually or after batch_pipeline
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["data-pipeline", "data-quality"],
)


def check_silver_quality(**kwargs):
    """Placeholder: Validate silver data schema, nulls, and types."""
    kwargs["ti"].log.info("Silver validation will be implemented in Phase 6")


def check_gold_quality(**kwargs):
    """Placeholder: Validate gold data referential integrity and value bounds."""
    kwargs["ti"].log.info("Gold validation will be implemented in Phase 6")


validate_silver = PythonOperator(
    task_id="validate_silver",
    python_callable=check_silver_quality,
    dag=dag,
)

validate_gold = PythonOperator(
    task_id="validate_gold",
    python_callable=check_gold_quality,
    dag=dag,
)

[validate_silver >> validate_gold]
