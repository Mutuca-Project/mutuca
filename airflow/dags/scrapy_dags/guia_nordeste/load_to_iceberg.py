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
        host="lakehouse-trino", # nome do serviço no docker compose
        port=8080,
        user="airflow",
        catalog="iceberg",
        schema="bronze"
    )

    cursor = trino_conn.cursor()

    bucket = "bronze"
    raw_path = f"{bucket}/lattes_raw/"
    processed_path = f"{raw_path}processed/" 

    # Busca apenas os arquivos .jsonl do lote autal
    files = fs.glob(f"{raw_path}lote_*.jsonl")

    for file_path in files:
        print(f"Lendo {file_path}...")

        with fs.open(file_path,"rb") as f:
            df = pd.read_json(f, lines=True)

        for _, row in df.iterrows():
                    # A query aceita os JSONs diretamente como strings (?)
                    insert_query = """
                        INSERT INTO lattes_raw (
                            id_lattes, nome, uf_atuacao, data_extracao, 
                            atuacoes_profissionais, projetos_pesquisa, producoes_bibliograficas
                        ) VALUES (
                            ?, ?, ?, CURRENT_TIMESTAMP, 
                            ?, ?, ?
                        )
                    """
                    
                    params = (
                        str(row['id_lattes']),
                        row['nome'],
                        row['uf_atuacao'],
                        json.dumps(row.get('profetional_performances', [])), # Chave do Scrapy
                        json.dumps(row.get('research_projects', [])),        # Chave do Scrapy
                        json.dumps(row.get('bibliographic_productions', [])) # Chave do Scrapy
                    )

                    cursor.execute(insert_query, params)

        filename = file_path.split("/")[-1]
        destine = f"{processed_path}{filename}"
        fs.cp_file(file_path, destine)
        fs.rm(file_path)

        print(f"Arquivo {filename} processado e movido.")

    trino_conn.close()




    

