import pandas as pd
import s3fs
import json
from trino.dbapi import connect
from airflow.hooks.base import BaseHook

TRINO_INSERT_BATCH_SIZE = 5  # conservador: JSONs Lattes podem chegar a ~1MB por linha


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
    raw_path = f"{bucket}/lattes_raw/"
    processed_path = f"{raw_path}processed/"

    files = fs.glob(f"{raw_path}lote_*.jsonl")

    if not files:
        raise FileNotFoundError(f"Nenhum arquivo lote_*.jsonl encontrado em {raw_path}")

    for file_path in files:
        print(f"Lendo {file_path}...")

        with fs.open(file_path, "rb") as f:
            df = pd.read_json(f, lines=True)

        rows = [
            (
                str(row["id_lattes"]),
                row["nome"],
                row["uf_atuacao"],
                json.dumps(row.get("profetional_performances", [])),
                json.dumps(row.get("research_projects", [])),
                json.dumps(row.get("bibliographic_productions", [])),
            )
            for _, row in df.iterrows()
        ]

        total = len(rows)
        for batch_start in range(0, total, TRINO_INSERT_BATCH_SIZE):
            batch = rows[batch_start: batch_start + TRINO_INSERT_BATCH_SIZE]
            placeholders = ", ".join(
                ["(?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)"] * len(batch)
            )
            insert_query = f"""
                INSERT INTO lattes_raw (
                    id_lattes, nome, uf_atuacao, data_extracao,
                    atuacoes_profissionais, projetos_pesquisa, producoes_bibliograficas
                ) VALUES {placeholders}
            """
            params = [v for row in batch for v in row]
            cursor.execute(insert_query, params)
            print(f"  Batch {batch_start + len(batch)}/{total} inserido.")

        filename = file_path.split("/")[-1]
        destine = f"{processed_path}{filename}"
        fs.cp_file(file_path, destine)
        fs.rm(file_path)

        print(f"Arquivo {filename} processado e movido para processed/.")

    trino_conn.close()
