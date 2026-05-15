from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

from shared.iceberg_loader import increment_offset, load_jsonl_to_iceberg

PIPELINES_DIR = Path(__file__).parent / "pipelines"

_BUILD_SCRIPT = """
echo "--- BUILD SCRAPY ---"
docker build -t lakehouse-scraper:latest /opt/airflow/project/scrapy
"""


def _build_scrapy_command(scrapy_cfg: dict, offset_cfg: dict | None) -> str:
    spider = scrapy_cfg["spider"]
    cmd = f"scrapy crawl {spider}"

    if offset_cfg:
        variable = offset_cfg["variable"]
        batch_size = offset_cfg["batch_size"]
        cmd += (
            f" -a offset={{{{ var.value.get('{variable}', 0) }}}}"
            f" -a batch_size={batch_size}"
        )

    for key, value in scrapy_cfg.get("settings", {}).items():
        cmd += f" -s {key}={value}"

    output = scrapy_cfg.get("output", "")
    if output:
        cmd += f" -O {output}"

    return cmd


def _build_mounts(mounts_cfg: list) -> list:
    return [
        Mount(
            source=m["source"],
            target=m["target"],
            type="bind",
            read_only=m.get("read_only", False),
        )
        for m in mounts_cfg
    ]


def create_dag(config: dict) -> DAG:
    dag_id = config["dag_id"]
    scrapy_cfg = config["scrapy"]
    load_cfg = config.get("load_iceberg")
    offset_cfg = config.get("offset_control")

    default_args = {
        "owner": config.get("owner", "mutuca"),
        "retries": config.get("retries", 1),
        "retry_delay": timedelta(minutes=5),
    }

    start_date = datetime.strptime(config.get("start_date", "2024-01-01"), "%Y-%m-%d")
    conn = BaseHook.get_connection("minio_s3_connection")

    dag = DAG(
        dag_id,
        default_args=default_args,
        description=config.get("description", ""),
        schedule_interval=config.get("schedule"),
        start_date=start_date,
        catchup=False,
        max_active_runs=1,
    )

    with dag:
        setup_env = BashOperator(
            task_id="setup_docker_env",
            bash_command=_BUILD_SCRIPT,
        )

        mounts = _build_mounts(scrapy_cfg.get("mounts", []))

        run_scraper = DockerOperator(
            task_id=f"crawl_{scrapy_cfg['spider']}",
            image="lakehouse-scraper:latest",
            container_name=f"scraper_{dag_id}_ephemeral",
            api_version="auto",
            auto_remove=True,
            mount_tmp_dir=False,
            network_mode="mutuca-lakehouse_lakehouse-net",
            command=_build_scrapy_command(scrapy_cfg, offset_cfg),
            environment={
                "AWS_ACCESS_KEY_ID": conn.login,
                "AWS_SECRET_ACCESS_KEY": conn.password,
                "AWS_ENDPOINT_URL": conn.extra_dejson.get("endpoint_url"),
                "AWS_REGION_NAME": "us-east-1",
                "AWS_EC2_METADATA_DISABLED": "true",
            },
            docker_url="unix://var/run/docker.sock",
            mounts=mounts,
        )

        chain = [setup_env, run_scraper]

        if load_cfg:
            chain.append(
                PythonOperator(
                    task_id="load_to_iceberg",
                    python_callable=load_jsonl_to_iceberg,
                    op_kwargs={
                        "source_glob": load_cfg["source_glob"],
                        "target_schema": load_cfg["target_schema"],
                        "target_table": load_cfg["target_table"],
                        "batch_size": load_cfg.get("batch_size", 100),
                        "rename": load_cfg.get("rename"),
                    },
                )
            )

        if offset_cfg:
            chain.append(
                PythonOperator(
                    task_id="increment_batch_offset",
                    python_callable=increment_offset,
                    op_kwargs={
                        "variable": offset_cfg["variable"],
                        "batch_size": offset_cfg["batch_size"],
                    },
                )
            )

        for i in range(len(chain) - 1):
            chain[i] >> chain[i + 1]

    return dag


for _yaml_file in PIPELINES_DIR.glob("*.yaml"):
    with open(_yaml_file) as _f:
        _config = yaml.safe_load(_f)
    _dag = create_dag(_config)
    globals()[_config["dag_id"]] = _dag
