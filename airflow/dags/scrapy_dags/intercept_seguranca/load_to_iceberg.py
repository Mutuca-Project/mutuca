import pandas as pd
import s3fs
from trino.dbapi import connect
from airflow.hooks.base import BaseHook


def load_jsonl_to_iceberg(**kwargs):
    s3_conn = BaseHook.get_connection("minio_s3_connection")
    s3_endpoint = s3_conn.extra_dejson.get("endpoint_url")

    fs = s3fs.S3FileSystem(
        key=s3_conn.login,
        secret=s3_conn.password,
        client_kwargs={"endpoint_url": s3_endpoint}
    )

    trino_conn = connect(
        host="lakehouse-trino",
        port=8080,
        user="airflow",
        catalog="iceberg",
        schema="bronze"
    )

    cursor = trino_conn.cursor()

    bucket = "bronze"
    raw_path = f"{bucket}/intercept_seguranca/"
    processed_path = f"{raw_path}processed/"

    # Busca apenas os arquivos .jsonl na raiz do raw_path, ignorando os já movidos
    files = [f for f in fs.glob(f"{raw_path}*.jsonl") if "processed" not in f]

    for file_path in files:
        print(f"Lendo {file_path}...")

        with fs.open(file_path,"rb") as f:
            df = pd.read_json(f, lines=True)
            
        # Substitui os NaN (Not a Number) nativos do Pandas por None (NULL no SQL)
        df = df.where(pd.notnull(df), None)

        for _, row in df.iterrows():
            # Utilizamos from_iso8601_timestamp pois o crawler já extraiu a data no formato ISO
            insert_query = """
                INSERT INTO intercept_seguranca (
                    url, manchete, lide, autores, 
                    data_publicacao, corpo_materia, data_extracao
                ) VALUES (
                    ?, ?, ?, ?, 
                    ?, ?, from_iso8601_timestamp(?)
                )
            """
            
            # Garante que autores seja passado como uma lista para o ARRAY(VARCHAR) do Trino
            autores = row.get('autores')
            if not isinstance(autores, list):
                autores = [] if autores is None else [autores]

            params = (
                row.get('url'),
                row.get('manchete'),
                row.get('lide'),
                autores,
                row.get('data_publicacao'),
                row.get('corpo_materia'),
                row.get('data_extracao')
            )

            cursor.execute(insert_query, params)

        # Move o arquivo para a pasta processed após a carga no Lakehouse
        filename = file_path.split("/")[-1]
        destine = f"{processed_path}{filename}"
        fs.cp_file(file_path, destine)
        fs.rm(file_path)

        print(f"Arquivo {filename} processado e movido para {destine}.")

    trino_conn.close()
