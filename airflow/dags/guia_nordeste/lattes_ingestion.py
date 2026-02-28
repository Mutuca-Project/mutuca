from datetime import timedelta, datetime
from airflow import DAG
from airflow.models import Variable
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.python import PythonOperator
from docker.types import Mount

default_args = {
    "owner": "ufpe-ova",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

BATCH_SIZE = 10000

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
    schedule_interval=None, # Podemos mudar para */5 * * * * para rodar automáticamente a cada 5 minutes
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1 # Impede concorrência para não estourar a RAM
) as dag:

    # 1. Extrai do SSD e joga no MinIO
    extract_lattes_task = DockerOperator(
        task_id= "extract_and_filter_lattes",
        image="lakehouse-scraper:latest", # Imagem que tem o Pandas, lxml e s3fs
        container_name="lattes_extractor_ephemeral",
        api_version="auto",
        auto_remove=True,
        network_mode="lakehouse-net",
        command=f"scrapy crawl lattes_ssd -a offset={{{{ var.value.get('lattes_offset', 0) }}}} -a batch_size={BATCH_SIZE} -O /app/data/lote_{{{{ ts_nodash }}}}.jsonl",
        docker_url="unix://var/run/docker.sock",
        environment={
            "AWS_ACCESS_KEY_ID": "{{ conn.minio_s3_connection.login }}",
            "AWS_SECRET_ACCESS_KEY": "{{ conn.minio_s3_connection.password }}",
            "AWS_ENDPOINT_URL": "{{ conn.minio_s3_connection.extra_dejson.get('endpoint_url') }}",
            "AWS_REGION_NAME": "us-east-1",
            "AWS_EC2_METADATA_DISABLED": "true",
        },
        mounts=[
            Mount(source='/home/datafixer/Workspace/repos/github/datafixer/mutuca/scrapy', target='/app', type='bind'),
            Mount(source='/media/datafixer/f57a7a83-c2e6-48e4-a82c-bdfa502ac0bf/cvs', target='/mnt/ssd_lattes', type='bind', read_only=True)
        ],
    )

    increment_offset_task = PythonOperator(
        task_id="increment_batch_offset",
        python_callable=increment_offset_func
    )

    extract_lattes_task >> increment_offset_task


