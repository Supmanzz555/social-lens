"""Custom Airflow operator for running Kafka producers."""

from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults
import subprocess
import os


class KafkaProducerOperator(BaseOperator):
    """Runs a Kafka producer script via 'uv run python' as an Airflow task."""

    @apply_defaults
    def __init__(
        self,
        producer_script: str,
        topic: str,
        limit: int = 25,
        project_dir: str = None,
        env_vars: dict = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.producer_script = producer_script
        self.topic = topic
        self.limit = limit
        self.project_dir = project_dir or "/opt/airflow"
        self.env_vars = env_vars or {}

    def execute(self, context):
        env = os.environ.copy()
        env.update(self.env_vars)

        cmd = f"uv run python {self.producer_script} --limit {self.limit}"
        self.log.info("Running producer: %s (in %s)", cmd, self.project_dir)

        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
            cwd=self.project_dir,
        )

        if result.returncode != 0:
            self.log.error("Producer failed: %s", result.stderr[-1000:])
            raise Exception(f"Producer failed with exit code {result.returncode}")

        self.log.info("Producer completed: %s", result.stdout[-500:])
        return result.stdout
