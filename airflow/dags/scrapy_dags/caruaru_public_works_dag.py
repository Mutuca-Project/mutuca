from datetime import datetime
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.bash import BashOperator

from docker.types import Mount

default_args = {
    "owner": "data_engineer",
    "start_date": datetime(2024, 1, 1),
    "retries": 1,
}

with DAG(
    "caruaru_public_works",
    default_args=default_args,
    schedule_interval=None,
    catchup=False,
) as dag :
    # Obtém as credências cadastradas via Aiflow Connections
    conn = BaseHook.get_connection("minio_s3_connection")
    conn_extra = conn.extra_dejson

    
    # --- 0. SETUP: Build das Imagens (Scrapy e dbt) ---
    # Ajuste os caminhos conforme a montagem do volume no docker-compose do Airflow
    # Assumindo que a raiz do projeto está visível.
    build_script = """
    echo "--- BUILD SCRAPY ---"
    # O contexto é a pasta 'scrapy' onde está o Dockerfile
    docker build -t lakehouse-scraper:latest /opt/airflow/project/scrapy
    
    #echo "--- BUILD DBT ---"
    ## O contexto é a pasta 'dbt' onde está o Dockerfile
    #docker build -t lakehouse-dbt:latest /opt/airflow/project/dbt
    """

    setup_env = BashOperator(
        task_id="0_setup_docker_env",
        bash_command=build_script
    )

    # --- 1. SCRAPY ---
    run_scraper = DockerOperator(
        task_id="rodar_scraper_quotes",
        image="lakehouse-scraper:latest",
        container_name="task_scraper_run",
        auto_remove=True,
        network_mode="mutuca-lakehouse_lakehouse-net",
        command="scrapy crawl public_works_cityhall -s HTTPCACHE_ENABLED=True",
        environment={
            "AWS_ACCESS_KEY_ID": conn.login,
            "AWS_SECRET_ACCESS_KEY": conn.password,
            "AWS_ENDPOINT_URL": conn_extra.get("endpoint_url"),
            "AWS_REGION_NAME": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
        },
        docker_url="unix://var/run/docker.sock"
    )

setup_env >> run_scraper
