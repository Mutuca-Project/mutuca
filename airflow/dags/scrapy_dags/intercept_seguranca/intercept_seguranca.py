from datetime import datetime, timedelta
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator

from airflow import DAG

from scrapy_dags.intercept_seguranca.load_to_iceberg import load_jsonl_to_iceberg 

default_args = {
    "owner": "mutuca-data",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    "ingestao_intercept_seguranca",
    default_args=default_args,
    description="Pipeline de raspagem e ingestão da editoria Segurança do The Intercept Brasil",
    schedule_interval=None,  # Execução manual para o Full Dump inicial
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1,
) as dag:

    # 1. SETUP: Compila a imagem Docker do Scrapy com os spiders atualizados
    build_script = """
    echo "--- BUILD SCRAPY ---"
    # O contexto é o diretório 'scrapy' mapeado no container do Airflow
    docker build --no-cache -t lakehouse-scraper:latest /opt/airflow/project/scrapy
    """

    setup_docker_env = BashOperator(
        task_id="setup_docker_env",
        bash_command=build_script,
    )

    # 2. EXTRAÇÃO: Executa o spider dentro do container e transmite via S3 API para o MinIO
    extract_intercept_task = DockerOperator(
        task_id="extract_intercept_seguranca",
        image="lakehouse-scraper:latest",
        container_name="intercept_scraper_ephemeral",
        api_version="auto",
        auto_remove=True,
        mount_tmp_dir=False,
        network_mode="mutuca-lakehouse_lakehouse-net",
        # O bot salva o log direto no MinIO. O {{ ts_nodash }} adiciona a data/hora do Airflow ao arquivo.
        command="scrapy crawl intercept_seguranca -s FEED_EXPORT_ENCODING=utf-8 -O s3://bronze/intercept_seguranca/materias_{{ ts_nodash }}.jsonl",
        docker_url="unix://var/run/docker.sock",
        environment={
            "AWS_ACCESS_KEY_ID": "{{ conn.minio_s3_connection.login }}",
            "AWS_SECRET_ACCESS_KEY": "{{ conn.minio_s3_connection.password }}",
            "AWS_ENDPOINT_URL": "{{ conn.minio_s3_connection.extra_dejson.get('endpoint_url') }}",
            "AWS_REGION_NAME": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
        },
        # Sem a propriedade 'mounts' aqui, pois os dados vêm da internet e vão direto para a rede interna (MinIO)
    )

    # 3. CARGA: Lê os arquivos do lote atual no MinIO e faz o INSERT no Trino/Iceberg
    load_to_iceberg_task = PythonOperator(
        task_id="load_to_iceberg",
        python_callable=load_jsonl_to_iceberg,
        provide_context=True
    )

    # Orquestração: define a ordem estrita de execução
    setup_docker_env >> extract_intercept_task >> load_to_iceberg_task
