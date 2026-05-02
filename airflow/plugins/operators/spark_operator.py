"""Custom Airflow operator for running local PySpark jobs."""

from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults
import subprocess
import os


class SparkJobOperator(BaseOperator):
    """Runs a local PySpark script via 'uv run python' as an Airflow task."""

    @apply_defaults
    def __init__(
        self,
        script_path: str,
        project_dir: str = None,
        spark_args: str = "",
        env_vars: dict = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.script_path = script_path
        self.project_dir = project_dir or "/opt/airflow"
        self.spark_args = spark_args
        self.env_vars = env_vars or {}

    def execute(self, context):
        env = os.environ.copy()
        env.update(self.env_vars)

        cmd = f"uv run python {self.spark_args} {self.script_path}"
        self.log.info("Running: %s (in %s)", cmd, self.project_dir)

        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
            cwd=self.project_dir,
        )

        if result.returncode != 0:
            self.log.error("Spark job failed: %s", result.stderr[-1000:])
            raise Exception(f"Spark job failed with exit code {result.returncode}")

        self.log.info("Spark job completed: %s", result.stdout[-500:])
        return result.stdout
