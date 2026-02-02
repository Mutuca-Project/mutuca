import os
from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from airflow.operators.python import PythonOperator # <--- Faltava importar isso
from airflow.hooks.base import BaseHook
from datetime import datetime
from docker.types import Mount

from scrapy_dags.silver_process_quotes import run_etl

# Configurações padrão
default_args = {
    'owner': 'data_engineer',
    'start_date': datetime(2024, 1, 1),
    'retries': 1,
}

with DAG(
    'ingestao_bronze_teste',
    default_args=default_args,
    schedule_interval=None,
    catchup=False
) as dag:

    conn = BaseHook.get_connection("minio_s3_connection")
    # Extrai o dicionario configurado no campo Extra da conexão. Importante para pegar o endpoint
    conn_extra = conn.extra_dejson

    # Tarefa: Rodar o container do Scrapy
    run_scraper = DockerOperator(
        task_id='rodar_scraper_quotes',
        image='lakehouse-scraper:latest',
        container_name='task_scraper_run',
        api_version='auto',
        auto_remove=True,
        # Rede: Importante para ele achar o MinIO pelo nome 'minio'
        network_mode='mutuca-lakehouse_lakehouse-net',
        # Comando Scrapy
        command='scrapy crawl teste_ingestao',
        # Variáveis de Ambiente para o Scrapy conectar no MinIO
        environment={
            'AWS_ACCESS_KEY_ID': conn.login,
            'AWS_SECRET_ACCESS_KEY': conn.password,
            'AWS_ENDPOINT_URL': conn_extra.get('endpoint_url'),
            'AWS_REGION_NAME': conn_extra.get('region_name', 'us-east-1'), 
            # Manter a flag para evitar timeout de metadata
            'AWS_EC2_METADATA_DISABLED': 'true',
        },
        # Montar volume é opcional, mas útil para debug
        docker_url='unix://var/run/docker.sock',
        mount_tmp_dir=False
    )
    
    load_to_bronze = PythonOperator(
        task_id="2_load_to_bronze_table",
        python_callable=run_etl
    )


    dbt_run = DockerOperator(
        task_id="3_transformation_silver_dbt",
        image="lakehouse-dbt:latest",
        container_name="task_dbt_run",
        api_version="auto",
        auto_remove=True,
        network_mode="mutuca-lakehouse_lakehouse-net",
        command="run --profiles-dir /root/.dbt --target prod",
        docker_url='unix://var/run/docker.sock',
        mount_tmp_dir=False
    )

    run_scraper >> load_to_bronze >> dbt_run

