import pandas as pd
import s3fs
import json
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
        host="trino_coordinator", # nome do serviço no docker compose
        port=8080,
        user="airflow",
        catalog="iceberg",
        schema="bronze"
    )

    cursor = trino_conn.cursor()

    bucket = "bronze"
    raw_path = f"{bucket}/lattes_raw"
    processed_path = f"{bucket}/processed/lattes_raw" 

    # Busca apenas os arquivos .jsonl do lote autal
    files = fs.glob(f"{raw_path}lote_*.jsonl")

    for file_path in files:
        print(f"Lendo {file_path}...")

        with fs.open(file_path,"rb") as f:
            df = pd.read_json(f, lines=True)

        for _, row in df.iterrows():
            insert_query = """
                            INSERT INTO lattes_raw (
                                id_lattes, nome, uf_atuacao, data_extracao, 
                                atuacoes_profissionais, projetos_pesquisa, producoes_bibliograficas
                            ) VALUES (
                                ?, ?, ?, CURRENT_TIMESTAMP, 
                                CAST(JSON_PARSE(?) AS ARRAY(ROW(instituicao VARCHAR, cargo VARCHAR, ano_inicio VARCHAR, ano_fim VARCHAR))),
                                CAST(JSON_PARSE(?) AS ARRAY(ROW(titulo VARCHAR, ano_inicio VARCHAR, situacao VARCHAR))),
                                CAST(JSON_PARSE(?) AS ARRAY(ROW(titulo VARCHAR, ano VARCHAR, tipo VARCHAR)))
                            )
                        """
            params = (
                str(row['id_lattes']),
                row['nome'],
                row['uf_atuacao'],
                json.dumps(row.get('atuacoes_profissionais', [])),
                json.dumps(row.get('projetos_pesquisa', [])),
                json.dumps(row.get('producoes_bibliograficas', []))
            )

            cursor.execute(insert_query, params)

        fs.rename(file_path, f"{processed_path}{filename}")
        filename = file_path.split("/")[-1]
        print(f"Arquivo {filename} processado e movido.")

    trino_conn.close()




    

