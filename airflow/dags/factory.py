from datetime import datetime, timedelta
from pathlib import Path

import yaml
from airflow.hooks.base import BaseHook
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.utils.trigger_rule import TriggerRule
from docker.types import Mount
from shared.iceberg_loader import increment_offset, load_jsonl_to_iceberg
from shared.nessie_client import create_branch as nessie_create_branch
from shared.nessie_client import delete_branch as nessie_delete_branch
from shared.nessie_client import merge_to_main as nessie_merge_to_main
from shared.rfb_csv_loader import load_csv_to_iceberg

from airflow import DAG

PIPELINES_DIR = Path(__file__).parent / "pipelines"

_BUILD_SCRAPY_SCRIPT = """
echo "--- BUILD SCRAPY ---"
docker build -t lakehouse-scraper:latest /opt/airflow/project/scrapy
"""

_BUILD_DBT_VALIDATOR_SCRIPT = """
echo "--- BUILD DBT VALIDATOR ---"
docker build -t lakehouse-dbt-validator:latest /opt/airflow/project/dbt/branch_validator
"""


# ---------------------------------------------------------------------------
# Callables de branching Nessie (ADR 007)
# ---------------------------------------------------------------------------


def _nessie_create_branch(dag_id: str, from_ref: str, **context) -> str:
    """
    Gera o nome da branch, cria no Nessie e retorna o nome via XCom.
    Convenção: ingest_{dag_id}_{YYYYMMDD_HHmmss} (ADR 007).
    O retorno é capturado automaticamente pelo Airflow como XCom.
    """
    ts = context["logical_date"].strftime("%Y%m%d_%H%M%S")
    branch_name = f"ingest_{dag_id}_{ts}"
    nessie_create_branch(branch_name, from_ref)
    return branch_name


def _nessie_merge(**context) -> None:
    """Faz merge da branch de ingestão para main."""
    branch_name = context["ti"].xcom_pull(task_ids="create_nessie_branch")
    nessie_merge_to_main(branch_name)


def _nessie_delete(**context) -> None:
    """
    Deleta a branch de ingestão. Roda com TriggerRule.ALL_DONE para
    garantir limpeza em ambos os caminhos: sucesso e falha (ADR 007).
    """
    branch_name = context["ti"].xcom_pull(task_ids="create_nessie_branch")
    nessie_delete_branch(branch_name)


# ---------------------------------------------------------------------------
# Helpers do factory
# ---------------------------------------------------------------------------


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

    # Argumentos do spider (-a key=value). Suportam Jinja (ex: Airflow Variables).
    # Uso: scrapy.args no YAML do pipeline (ex: de, ate para o CGU).
    for key, value in scrapy_cfg.get("args", {}).items():
        cmd += f" -a {key}={value}"

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


# ---------------------------------------------------------------------------
# Factory principal
# ---------------------------------------------------------------------------


def create_dag(config: dict) -> DAG:
    dag_id = config["dag_id"]
    scrapy_cfg = config.get("scrapy")  # opcional: ausente em pipelines sem scraping
    load_cfg = config.get("load_iceberg")
    load_csv_cfg = config.get("load_csv")  # loader CSV do HD externo (ex: RFB CNPJ)
    offset_cfg = config.get("offset_control")
    branching_cfg = config.get("branching")
    branching_enabled = bool(branching_cfg and branching_cfg.get("enabled"))

    if branching_enabled and not load_cfg and not load_csv_cfg:
        raise ValueError(
            f"DAG '{dag_id}': branching.enabled=true requer a seção "
            "load_iceberg ou load_csv definida no YAML."
        )

    if load_csv_cfg and not branching_enabled:
        raise ValueError(
            f"DAG '{dag_id}': load_csv requer branching.enabled=true. "
            "A carga de CSVs do HD externo só opera via branch Nessie isolada."
        )

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
        schedule=config.get("schedule"),
        start_date=start_date,
        catchup=False,
        max_active_runs=1,
    )

    with dag:

        # --- Branching: cria branch antes de tudo ---
        if branching_enabled:
            from_ref = branching_cfg.get("from_ref", "main")
            create_branch_task = PythonOperator(
                task_id="create_nessie_branch",
                python_callable=_nessie_create_branch,
                op_kwargs={"dag_id": dag_id, "from_ref": from_ref},
            )

        # --- Setup e Scrapy (opcionais) ---
        # Pipelines sem seção scrapy (ex: rfb_cnpj — dados já no HD)
        # não geram setup_docker_env nem crawl_*.
        if scrapy_cfg:
            setup_env = BashOperator(
                task_id="setup_docker_env",
                bash_command=_BUILD_SCRAPY_SCRIPT,
            )

            run_scraper = DockerOperator(
                task_id=f"crawl_{scrapy_cfg['spider']}",
                image="lakehouse-scraper:latest",
                container_name=f"scraper_{dag_id}_ephemeral",
                api_version="auto",
                auto_remove="force",
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
                mounts=_build_mounts(scrapy_cfg.get("mounts", [])),
            )

        if branching_enabled:
            build_dbt_validator = BashOperator(
                task_id="build_dbt_validator",
                bash_command=_BUILD_DBT_VALIDATOR_SCRIPT,
            )

        # --- Grafo de dependências: scraping ---
        if scrapy_cfg:
            if branching_enabled:
                # [create_nessie_branch →] setup_docker_env + build_dbt_validator → crawl_*
                create_branch_task >> setup_env
                create_branch_task >> build_dbt_validator
                [setup_env, build_dbt_validator] >> run_scraper
            else:
                setup_env >> run_scraper
            last_ingestion_task = run_scraper
        else:
            # Sem scrapy: branch → build_dbt_validator (sem crawl)
            if branching_enabled:
                last_ingestion_task = build_dbt_validator
            else:
                last_ingestion_task = None

        # --- Load CSV do HD externo (ex: RFB CNPJ) ---
        if load_csv_cfg:
            load_csv_task = PythonOperator(
                task_id="load_csv_to_iceberg",
                python_callable=load_csv_to_iceberg,
                op_kwargs={
                    "source_mount": load_csv_cfg["source_mount"],
                    "tables": load_csv_cfg["tables"],
                    "chunk_size": load_csv_cfg.get("chunk_size", 500_000),
                    "encoding": load_csv_cfg.get("encoding", "latin-1"),
                    "separator": load_csv_cfg.get("separator", ";"),
                },
            )
            if last_ingestion_task:
                last_ingestion_task >> load_csv_task
            elif branching_enabled:
                create_branch_task >> load_csv_task
            last_ingestion_task = load_csv_task

        # --- Load Iceberg (JSONL — caminho original) ---
        if load_cfg:
            load_task = PythonOperator(
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
            if last_ingestion_task:
                last_ingestion_task >> load_task
            last_ingestion_task = load_task

            if branching_enabled:
                # Grafo de branching:
                #
                # [load_csv_to_iceberg |] load_to_iceberg → dbt_test_branch → merge_to_main → [increment_offset] → delete_branch
                #         └────────────────────────────────────────────────────────────────────────────────────────────────────┘
                #                                    (ALL_DONE garante cleanup em falhas)
                #
                # Se dbt_test_branch falhar (dados ruins), merge é bloqueado e delete
                # limpa a branch isolada — os dados ruins nunca chegam a main (ADR 007).

                nessie_iceberg_endpoint = branching_cfg.get(
                    "nessie_iceberg_endpoint", "http://lakehouse-nessie:19120/iceberg/"
                )
                minio_endpoint = conn.extra_dejson.get(
                    "endpoint_url", "http://lakehouse-minio:9000"
                )

                dbt_test_task = DockerOperator(
                    task_id="dbt_test_branch",
                    image="lakehouse-dbt-validator:latest",
                    container_name=f"dbt_validator_{dag_id}_ephemeral",
                    api_version="auto",
                    auto_remove="force",
                    mount_tmp_dir=False,
                    network_mode="mutuca-lakehouse_lakehouse-net",
                    # Código baked-in na imagem (build em build_dbt_validator).
                    # WORKDIR=/dbt/branch_validator — profiles.yml resolvido automaticamente.
                    command=(
                        "dbt test "
                        "--target branch_validation "
                        "--select source:bronze"
                    ),
                    environment={
                        "NESSIE_ICEBERG_ENDPOINT": nessie_iceberg_endpoint,
                        # XCom do create_nessie_branch — Jinja resolvido pelo Airflow
                        "NESSIE_BRANCH": (
                            "{{ ti.xcom_pull(task_ids='create_nessie_branch') }}"
                        ),
                        "MINIO_ENDPOINT": minio_endpoint,
                        "MINIO_ACCESS_KEY": conn.login,
                        "MINIO_SECRET_KEY": conn.password,
                    },
                    docker_url="unix://var/run/docker.sock",
                )

                merge_task = PythonOperator(
                    task_id="merge_to_main",
                    python_callable=_nessie_merge,
                )
                delete_task = PythonOperator(
                    task_id="delete_branch",
                    python_callable=_nessie_delete,
                    trigger_rule=TriggerRule.ALL_DONE,
                )

                # last_ingestion_task aponta para o último task de carga
                # (load_to_iceberg ou load_csv_to_iceberg, dependendo do YAML)
                last_ingestion_task >> dbt_test_task >> merge_task
                last_success_task = merge_task

                if offset_cfg:
                    offset_task = PythonOperator(
                        task_id="increment_batch_offset",
                        python_callable=increment_offset,
                        op_kwargs={
                            "variable": offset_cfg["variable"],
                            "batch_size": offset_cfg["batch_size"],
                        },
                    )
                    merge_task >> offset_task
                    last_success_task = offset_task

                # delete depende do último task do caminho de sucesso
                # e do primeiro task de carga (cleanup em caso de falha no load ou no dbt)
                last_success_task >> delete_task
                last_ingestion_task >> delete_task

            else:
                # Sem branching: fluxo original
                if offset_cfg:
                    offset_task = PythonOperator(
                        task_id="increment_batch_offset",
                        python_callable=increment_offset,
                        op_kwargs={
                            "variable": offset_cfg["variable"],
                            "batch_size": offset_cfg["batch_size"],
                        },
                    )
                    last_ingestion_task >> offset_task

    return dag


for _yaml_file in PIPELINES_DIR.glob("*.yaml"):
    with open(_yaml_file) as _f:
        _config = yaml.safe_load(_f)
    _dag = create_dag(_config)
    globals()[_config["dag_id"]] = _dag
