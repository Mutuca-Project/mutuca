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

    # 1. Compila a imagem Docker do Scrapy
    build_scrapy_image = """
    echo "--- BUILD SCRAPY ---"
    docker build --no-cache -t lakehouse-scraper:latest /opt/airflow/project/scrapy
    """
    # 2. Setup do ambiente Scrapy
    setup_scrapy_env = BashOperator(
        task_id="setup_scrapy_env",
        bash_command=build_scrapy_image,
    )

    # 3. EXTRAÇÃO: Executa o spider dentro do container e transmite via S3 API para o MinIO
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
    )

    # 4. CARGA: Lê os arquivos do lote atual no MinIO e faz o INSERT no Trino/Iceberg
    load_to_iceberg_task = PythonOperator(
        task_id="load_to_iceberg",
        python_callable=load_jsonl_to_iceberg,
        provide_context=True
    )

    # 5. Compila a imagem do DBT
    build_dbt_image = """
    echo "--- BUILD DBT ---"
    docker build --no-cache -t lakehouse-dbt:latest /opt/airflow/project/dbt
    """
    # 6. Setup do ambiente Scrapy
    setup_dbt_env = BashOperator(
        task_id="setup_dbt_env",
        bash_command=build_dbt_image,
    )
    # 7. TRANSFORMAÇÃO: dbt (Camada Silver)
    dbt_silver_task = DockerOperator(
        task_id="transformation_silver_dbt",
        image="lakehouse-dbt:latest",
        container_name="intercept_dbt_silver_ephemeral",
        api_version="auto",
        auto_remove=True,
        mount_tmp_dir=False, # Evita erro de mount do /tmp no DooD
        network_mode="mutuca-lakehouse_lakehouse-net",
        # O parâmetro --select garante que apenas o modelo do intercept seja executado, economizando processamento.
        command="run --select silver_intercept_seguranca --profiles-dir . --project-dir . --target prod",
        docker_url="unix://var/run/docker.sock"
    )

    # Orquestração: define a ordem estrita de execução
    setup_scrapy_env >> extract_intercept_task >> load_to_iceberg_task >> setup_dbt_env >> dbt_silver_task
