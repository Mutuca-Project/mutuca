import json

import pandas as pd
import s3fs
from airflow.hooks.base import BaseHook
from trino.dbapi import connect

TRINO_HOST = "lakehouse-trino"
TRINO_PORT = 8080
TRINO_USER = "airflow"
TRINO_CATALOG = "iceberg"


def _coerce(value) -> str | None:
    """Converte um valor Python para str compatível com Trino VARCHAR."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return str(value)


def load_jsonl_to_iceberg(
    source_glob: str,
    target_schema: str,
    target_table: str,
    batch_size: int = 100,
    rename: dict | None = None,
    **context,
):
    """
    Carrega arquivos JSONL do MinIO em uma tabela Iceberg via Trino.

    Todos os campos presentes no JSONL são inseridos automaticamente — não é necessário
    declarar o schema no YAML. Tipos complexos (dict, list) são serializados com
    json.dumps para VARCHAR. A coluna data_extracao é sempre adicionada via
    CURRENT_TIMESTAMP e não deve ser declarada no JSONL nem no pipeline YAML.

    Parâmetros:
        source_glob:   Caminho glob no MinIO (ex: "bronze/lattes_raw/lote_*.jsonl").
        target_schema: Schema Iceberg alvo (ex: "bronze").
        target_table:  Tabela Iceberg alvo (ex: "lattes_raw").
        batch_size:    Linhas por INSERT. Reduza para 50 se os JSONs forem grandes.
        rename:        Renomeação opcional de campos do JSONL para colunas da tabela
                       (ex: {"profetional_performances": "atuacoes_profissionais"}).

    PRÉ-REQUISITO: a tabela alvo deve existir no Trino antes da primeira execução.
    Este módulo apenas insere dados — ele não cria nem altera tabelas.
    Use CREATE TABLE no Trino com o schema esperado antes de ativar o pipeline.
    """
    s3_conn = BaseHook.get_connection("minio_s3_connection")
    fs = s3fs.S3FileSystem(
        key=s3_conn.login,
        secret=s3_conn.password,
        client_kwargs={"endpoint_url": s3_conn.extra_dejson.get("endpoint_url")},
    )

    trino_conn = connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog=TRINO_CATALOG,
        schema=target_schema,
    )
    cursor = trino_conn.cursor()

    base_path = source_glob.rsplit("/", 1)[0]
    processed_path = f"{base_path}/processed"

    files = fs.glob(source_glob)
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo encontrado em {source_glob}")

    for file_path in files:
        print(f"Lendo {file_path}...")
        with fs.open(file_path, "rb") as f:
            df = pd.read_json(f, lines=True)

        if rename:
            df = df.rename(columns=rename)

        columns = list(df.columns)
        col_names_sql = ", ".join(["data_extracao"] + columns)
        row_placeholder = f"(CURRENT_TIMESTAMP, {', '.join(['?'] * len(columns))})"

        rows = [
            tuple(_coerce(row[col]) for col in columns)
            for _, row in df.iterrows()
        ]

        total = len(rows)
        for i in range(0, total, batch_size):
            batch = rows[i : i + batch_size]
            placeholders = ", ".join([row_placeholder] * len(batch))
            params = [v for row in batch for v in row]
            cursor.execute(
                f"INSERT INTO {target_table} ({col_names_sql}) VALUES {placeholders}",
                params,
            )
            print(f"  [{file_path.split('/')[-1]}] Batch {i + len(batch)}/{total} inserido.")

        filename = file_path.split("/")[-1]
        dest = f"{processed_path}/{filename}"
        fs.cp_file(file_path, dest)
        fs.rm(file_path)
        print(f"Arquivo {filename} movido para processed/.")

    trino_conn.close()


def increment_offset(variable: str, batch_size: int, **context):
    from airflow.models import Variable

    current = int(Variable.get(variable, default_var=0))
    Variable.set(variable, current + batch_size)
    print(f"Offset {variable}: {current} → {current + batch_size}")
