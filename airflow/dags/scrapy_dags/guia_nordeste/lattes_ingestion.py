from datetime import datetime, timedelta
from airflow.operators.bash import BashOperator
from airflow.models import Variable
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

from airflow import DAG

default_args = {
    "owner": "ufpe-ova",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

BATCH_SIZE = 100000

def increment_offset_func():
    """Lê o offset atual e incrementa para a próxima execução da DAG."""
    current_offset = int(Variable.get("lattes_offset", default_var=0))
    next_offset = current_offset + BATCH_SIZE
    Variable.set("lattes_offset", next_offset)
    print(f"Offset atualizado: de {current_offset} para {next_offset}")

with DAG(
    "ingestao_lattes_ssd",
    default_args=default_args,
    description="Pipeline de ingestão em lotes do Lattes via SSD externo",
    schedule_interval=None,  # Pode alterar para '*/5 * * * *' para automatizar
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1,  # Essencial: impede a concorrência para proteger a RAM
) as dag:

    # 1. SETUP: Compila a imagem Docker atualizada. 
    build_script = """
    echo "--- BUILD SCRAPY ---"
    # O contexto é a diretoria 'scrapy' visível para o container do Airflow
    docker build --no-cache -t lakehouse-scraper:latest /opt/airflow/project/scrapy
    """

    setup_env = BashOperator(
        task_id="setup_docker_env",
        bash_command=build_script,
    )

    # 2. EXTRAÇÃO: Lê o SSD e grava em stream para o MinIO
    extract_lattes_task = DockerOperator(
        task_id="extract_and_filter_lattes",
        image="lakehouse-scraper:latest",
        container_name="lattes_extractor_ephemeral",
        api_version="auto",
        auto_remove=True,
        mount_tmp_dir=False,
        network_mode="mutuca-lakehouse_lakehouse-net",
        # O ficheiro será enviado diretamente para o MinIO sem tocar no disco.
        command=f"scrapy crawl lattes_ssd -a offset={{{{ var.value.get('lattes_offset', 0) }}}} -a batch_size={BATCH_SIZE} -s DOWNLOAD_DELAY=0 -s CONCURRENT_REQUESTS=32 -O s3://bronze/lattes_raw/lote_{{{{ ts_nodash }}}}.jsonl",
        docker_url="unix://var/run/docker.sock",
        environment={
            "AWS_ACCESS_KEY_ID": "{{ conn.minio_s3_connection.login }}",
            "AWS_SECRET_ACCESS_KEY": "{{ conn.minio_s3_connection.password }}",
            "AWS_ENDPOINT_URL": "{{ conn.minio_s3_connection.extra_dejson.get('endpoint_url') }}",
            "AWS_REGION_NAME": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
        },
        mounts=[
            # Mapeamento de leitura do SSD.
            Mount(
                source="/media/datafixer/f57a7a83-c2e6-48e4-a82c-bdfa502ac0bf/cvs",
                target="/mnt/ssd_lattes",
                type="bind",
                read_only=True,
            ),
        ],
    )

    ## DEBUG

    debug_conn_task = BashOperator(
            task_id="debug_minio_connection",
            bash_command="""
            echo "=== DEBUG DAS VARIÁVEIS ==="
            echo "Endpoint URL: {{ conn.minio_s3_connection.extra_dejson.get('endpoint_url') }}"
            echo "Login (Access Key): {{ conn.minio_s3_connection.login }}"
            # A senha a gente evita printar, mas se for ambiente local de teste:
            echo "Senha (Secret Key): {{ conn.minio_s3_connection.password }}"
            echo "==========================="
            """
        )
    # 3. CONTROLE: Atualiza o marcador (Offset) para o lote seguinte
    increment_offset_task = PythonOperator(
        task_id="increment_batch_offset", python_callable=increment_offset_func
    )

    setup_env >> extract_lattes_task >> increment_offset_task

