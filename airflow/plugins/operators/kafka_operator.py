"""
Custom Airflow operator for running Kafka producers.
"""

from airflow.models import BaseOperator
from airflow.utils.decorators import apply_defaults


class KafkaProducerOperator(BaseOperator):
    """Runs a Kafka producer script as an Airflow task."""

    @apply_defaults
    def __init__(
        self,
        producer_script: str,
        topic: str,
        limit: int = 25,
        env_vars: dict = None,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.producer_script = producer_script
        self.topic = topic
        self.limit = limit
        self.env_vars = env_vars or {}

    def execute(self, context):
        import subprocess
        import os

        env = os.environ.copy()
        env.update(self.env_vars)

        cmd = f"python {self.producer_script} --limit {self.limit}"
        self.log.info(f"Running producer: {cmd}")

        result = subprocess.run(
            cmd,
            shell=True,
            env=env,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            self.log.error(f"Producer failed: {result.stderr}")
            raise Exception(f"Producer failed with exit code {result.returncode}")

        self.log.info(f"Producer completed: {result.stdout}")
        return result.stdout
