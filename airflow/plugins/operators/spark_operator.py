"""
Custom Airflow operator for running local PySpark jobs.
"""

from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults


class SparkSubmitOperator(BaseOperator):
    """Runs a local PySpark script as an Airflow task."""

    @apply_defaults
    def __init__(
        self,
        script_path: str,
        spark_args: str = "",
        env_vars: dict = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.script_path = script_path
        self.spark_args = spark_args
        self.env_vars = env_vars or {}

    def execute(self, context):
        import subprocess
        import os

        env = os.environ.copy()
        env.update(self.env_vars)

        cmd = f"spark-submit {self.spark_args} {self.script_path}"
        self.log.info(f"Running: {cmd}")

        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            self.log.error(f"Spark job failed: {result.stderr}")
            raise Exception(f"Spark job failed with exit code {result.returncode}")

        self.log.info(f"Spark job completed: {result.stdout}")
        return result.stdout
