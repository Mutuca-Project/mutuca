"""
iceberg_loader.py — Loader genérico de dados JSONL para tabelas Iceberg.

Dois caminhos de escrita (selecionados automaticamente via XCom):

  • PyIceberg + RestCatalog com prefix=branch_name  (branching habilitado no YAML)
    Escreve na branch de ingestão isolada antes do merge para main (ADR 007).

  • Trino INSERT (sem branching)
    Comportamento original: escreve diretamente em main.

PRÉ-REQUISITO: a tabela alvo deve existir antes da primeira execução.
Este módulo apenas insere dados — não cria nem altera tabelas.
"""

import json
import os
from datetime import datetime, timezone

import pandas as pd
import s3fs
from airflow.hooks.base import BaseHook
from trino.dbapi import connect

TRINO_HOST = "lakehouse-trino"
TRINO_PORT = 8080
TRINO_USER = "airflow"
TRINO_CATALOG = "iceberg"

# URI do endpoint Iceberg REST do Nessie (dentro da rede Docker)
NESSIE_ICEBERG_URI = os.getenv("NESSIE_ICEBERG_ENDPOINT", "http://nessie:19120/iceberg/")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce(value) -> str | None:
    """Converte um valor Python para str compatível com Trino/Iceberg VARCHAR."""
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


def _pyiceberg_catalog(branch_name: str, s3_conn):
    """Retorna um RestCatalog PyIceberg apontando para a branch especificada."""
    from pyiceberg.catalog.rest import RestCatalog

    return RestCatalog(
        name="nessie",
        uri=NESSIE_ICEBERG_URI,
        prefix=branch_name,
        **{
            "s3.endpoint": s3_conn.extra_dejson.get("endpoint_url"),
            "s3.access-key-id": s3_conn.login,
            "s3.secret-access-key": s3_conn.password,
            "s3.path-style-access": "true",
        },
    )


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def load_jsonl_to_iceberg(
    source_glob: str,
    target_schema: str,
    target_table: str,
    batch_size: int = 100,
    rename: dict | None = None,
    **context,
):
    """
    Carrega arquivos JSONL do MinIO em uma tabela Iceberg.

    Quando executada num DAG com branching habilitado (ADR 007), lê o nome
    da branch via XCom da task 'create_nessie_branch' e usa PyIceberg para
    escrever na branch isolada. Sem branching, usa o caminho Trino original.

    Parâmetros:
        source_glob:   Caminho glob no MinIO (ex: "bronze/lattes_raw/lote_*.jsonl").
        target_schema: Schema Iceberg alvo (ex: "bronze").
        target_table:  Tabela Iceberg alvo (ex: "lattes_raw").
        batch_size:    Linhas por INSERT no caminho Trino. Ignorado no caminho
                       PyIceberg (cada arquivo JSONL gera um único arquivo Parquet).
        rename:        Renomeação opcional de campos do JSONL para colunas da tabela.
    """
    ti = context.get("ti")
    branch_name = ti.xcom_pull(task_ids="create_nessie_branch") if ti else None

    s3_conn = BaseHook.get_connection("minio_s3_connection")
    fs = s3fs.S3FileSystem(
        key=s3_conn.login,
        secret=s3_conn.password,
        client_kwargs={"endpoint_url": s3_conn.extra_dejson.get("endpoint_url")},
    )

    base_path = source_glob.rsplit("/", 1)[0]
    processed_path = f"{base_path}/processed"

    files = fs.glob(source_glob)
    if not files:
        raise FileNotFoundError(f"Nenhum arquivo encontrado em {source_glob}")

    if branch_name:
        _load_via_pyiceberg(
            files, fs, processed_path, branch_name, s3_conn,
            target_schema, target_table, rename,
        )
    else:
        _load_via_trino(
            files, fs, processed_path,
            target_schema, target_table, batch_size, rename,
        )


def _load_via_pyiceberg(
    files, fs, processed_path, branch_name, s3_conn,
    target_schema, target_table, rename,
):
    """Escrita via PyIceberg na branch de ingestão isolada (ADR 007)."""
    import pyarrow as pa

    catalog = _pyiceberg_catalog(branch_name, s3_conn)
    iceberg_table = catalog.load_table(f"{target_schema}.{target_table}")

    # Tabelas criadas via Trino podem não ter write.parquet.compression-codec
    # definido no metadata Iceberg (o codec fica só no catálogo do Trino).
    # PyIceberg lê a propriedade vazia e o PyArrow falha ao criar o ParquetWriter.
    # Solução: setar zstd explicitamente via transaction (operação idempotente).
    if not iceberg_table.properties.get("write.parquet.compression-codec"):
        with iceberg_table.transaction() as tx:
            tx.set_properties({"write.parquet.compression-codec": "zstd"})
        iceberg_table = catalog.load_table(f"{target_schema}.{target_table}")
        print("  Propriedade write.parquet.compression-codec=zstd definida na tabela.")

    for file_path in files:
        print(f"[branch={branch_name}] Lendo {file_path}...")
        with fs.open(file_path, "rb") as f:
            df = pd.read_json(f, lines=True)

        if rename:
            df = df.rename(columns=rename)

        # Coerce para str (mesmo comportamento do caminho Trino)
        for col in df.columns:
            df[col] = df[col].apply(_coerce)

        # Adiciona data_extracao como primeira coluna
        df.insert(0, "data_extracao", datetime.now(timezone.utc))

        # Converte para PyArrow e anexa à tabela na branch
        # PyIceberg mapeia colunas por nome — ordem não é crítica
        arrow_df = pa.Table.from_pandas(df, preserve_index=False)
        iceberg_table.append(arrow_df)

        filename = file_path.split("/")[-1]
        print(f"  {filename}: {len(df)} linhas inseridas na branch '{branch_name}'.")

        dest = f"{processed_path}/{filename}"
        fs.cp_file(file_path, dest)
        fs.rm(file_path)
        print(f"  {filename} movido para processed/.")


def _load_via_trino(
    files, fs, processed_path,
    target_schema, target_table, batch_size, rename,
):
    """Escrita via Trino INSERT direto em main (sem branching)."""
    trino_conn = connect(
        host=TRINO_HOST,
        port=TRINO_PORT,
        user=TRINO_USER,
        catalog=TRINO_CATALOG,
        schema=target_schema,
    )
    cursor = trino_conn.cursor()

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
        print(f"  {filename} movido para processed/.")

    trino_conn.close()


# ---------------------------------------------------------------------------
# Offset control
# ---------------------------------------------------------------------------

def increment_offset(variable: str, batch_size: int, **context):
    from airflow.models import Variable

    current = int(Variable.get(variable, default_var=0))
    Variable.set(variable, current + batch_size)
    print(f"Offset {variable}: {current} → {current + batch_size}")
