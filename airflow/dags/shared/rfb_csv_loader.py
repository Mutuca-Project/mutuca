"""
rfb_csv_loader.py — Loader de CSVs da Receita Federal para tabelas Iceberg.

Diferenças em relação ao iceberg_loader.py (JSONL genérico):
  • Fonte: CSVs no HD externo montado no container Airflow (/mnt/hd_rfb)
  • Formato: sem header, encoding latin-1, separador ponto-e-vírgula
  • Múltiplas tabelas por execução (Empresas, Estabelecimentos, Socios)
  • Leitura em chunks para controle de memória (arquivos de vários GBs)

Fluxo de execução:
  Para cada tabela declarada no YAML (load_csv.tables):
    1. Lista os arquivos CSV no HD que correspondem ao file_pattern
    2. Para cada arquivo, lê em chunks de chunk_size linhas
    3. Adiciona coluna data_extracao (timestamp UTC)
    4. Converte para PyArrow Table e appenda na branch Nessie via PyIceberg

PRÉ-REQUISITO: as três tabelas Iceberg devem existir antes da primeira execução.
Ver: sql/create_tables_rfb_cnpj.sql
"""

import glob
import os
import time
from datetime import datetime, timezone

import pandas as pd
import pyarrow as pa
from airflow.hooks.base import BaseHook
from pyiceberg.catalog.rest import RestCatalog

# Endpoint Iceberg REST do Nessie (rede interna Docker)
NESSIE_ICEBERG_URI = os.getenv("NESSIE_ICEBERG_ENDPOINT", "http://lakehouse-nessie:19120/iceberg/")


# ---------------------------------------------------------------------------
# Layouts oficiais da Receita Federal
# Fonte: https://www.gov.br/receitafederal/dados/cnpj-metadados.pdf
# Os CSVs não têm linha de cabeçalho — a ordem das colunas é fixada pelo layout.
# ---------------------------------------------------------------------------

COLUNAS_EMPRESAS = [
    "cnpj_basico",
    "razao_social",
    "natureza_juridica",
    "qualificacao_responsavel",
    "capital_social",
    "porte_empresa",
    "ente_federativo_responsavel",
]

COLUNAS_ESTABELECIMENTOS = [
    "cnpj_basico",
    "cnpj_ordem",
    "cnpj_dv",
    "identificador_matriz_filial",
    "nome_fantasia",
    "situacao_cadastral",
    "data_situacao_cadastral",
    "motivo_situacao_cadastral",
    "nome_cidade_exterior",
    "pais",
    "data_inicio_atividade",
    "cnae_fiscal_principal",
    "cnae_fiscal_secundaria",
    "tipo_logradouro",
    "logradouro",
    "numero",
    "complemento",
    "bairro",
    "cep",
    "uf",
    "municipio",
    "ddd1",
    "telefone1",
    "ddd2",
    "telefone2",
    "ddd_fax",
    "fax",
    "correio_eletronico",
    "situacao_especial",
    "data_situacao_especial",
]

COLUNAS_SOCIOS = [
    "cnpj_basico",
    "identificador_socio",
    "nome_socio_razao_social",
    "cpf_cnpj_socio",
    "qualificacao_socio",
    "data_entrada_sociedade",
    "pais",
    "representante_legal",
    "nome_do_representante",
    "qualificacao_representante_legal",
    "faixa_etaria",
]

# Mapeia sufixo do file_pattern → lista de colunas.
# Chaves correspondem ao sufixo real dos arquivos extraídos do ZIP da RFB:
#   *.EMPRECSV  → Empresas
#   *.ESTABELE  → Estabelecimentos
#   *.SOCIOCSV  → Socios
_COLUNAS_POR_PADRAO: dict[str, list[str]] = {
    "EMPRECSV": COLUNAS_EMPRESAS,
    "ESTABELE": COLUNAS_ESTABELECIMENTOS,
    "SOCIOCSV": COLUNAS_SOCIOS,
}


def _resolver_colunas(file_pattern: str) -> list[str]:
    """
    Retorna a lista de colunas correspondente ao file_pattern declarado no YAML.
    Lança ValueError se o padrão não for reconhecido.
    """
    for prefixo, colunas in _COLUNAS_POR_PADRAO.items():
        if prefixo in file_pattern:
            return colunas
    raise ValueError(
        f"Nenhum layout de colunas encontrado para file_pattern='{file_pattern}'. "
        f"Padrões suportados: {list(_COLUNAS_POR_PADRAO.keys())}"
    )


def _catalog(branch_name: str, s3_conn) -> RestCatalog:
    """Retorna RestCatalog PyIceberg apontando para a branch especificada."""
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


def _arrow_schema(colunas: list[str]) -> pa.Schema:
    """
    Schema PyArrow explícito para a conversão pandas → PyArrow.

    Sem schema explícito, colunas inteiramente vazias num chunk são inferidas
    como pa.null() pelo PyArrow, tipo não suportado pelo PyIceberg
    (TypeError: Unsupported type: null).

    Estratégia: data_extracao → timestamp us/UTC; todo o resto → string.
    """
    fields = [pa.field("data_extracao", pa.timestamp("us", tz="UTC"))]
    fields += [pa.field(col, pa.string()) for col in colunas]
    return pa.schema(fields)


def _append_com_retry(iceberg_table, arrow_table, max_tentativas: int = 4):
    """
    Wrapper de retry com backoff exponencial para iceberg_table.append().

    Necessário porque o MinIO em HD externo (USB) pode levar mais tempo para
    liberar I/O entre gravações, causando timeout S3 (OSError curlCode: 28)
    durante a iniciação do multipart upload.

    Estratégia de espera: 30s → 60s → 120s → falha definitiva.
    """
    for tentativa in range(1, max_tentativas + 1):
        try:
            iceberg_table.append(arrow_table)
            return
        except OSError as e:
            if tentativa == max_tentativas:
                raise
            espera = 30 * (2 ** (tentativa - 1))   # 30, 60, 120 segundos
            print(
                f"    [retry {tentativa}/{max_tentativas - 1}] OSError S3: {e}\n"
                f"    Aguardando {espera}s antes de tentar novamente..."
            )
            time.sleep(espera)


def _garantir_codec(iceberg_table, catalog, schema: str, table: str):
    """
    Tabelas criadas via Trino podem não ter write.parquet.compression-codec
    no metadata Iceberg. PyIceberg falha ao criar ParquetWriter sem o codec.
    Solução: setar zstd explicitamente (operação idempotente).
    Mesmo padrão adotado em iceberg_loader.py.
    """
    if not iceberg_table.properties.get("write.parquet.compression-codec"):
        with iceberg_table.transaction() as tx:
            tx.set_properties({"write.parquet.compression-codec": "zstd"})
        iceberg_table = catalog.load_table(f"{schema}.{table}")
        print(f"  Codec zstd definido em {schema}.{table}.")
    return iceberg_table


# ---------------------------------------------------------------------------
# Função principal — chamada pelo factory.py como PythonOperator
# ---------------------------------------------------------------------------

def load_csv_to_iceberg(
    source_mount: str,
    tables: list[dict],
    chunk_size: int = 500_000,
    encoding: str = "latin-1",
    separator: str = ";",
    **context,
):
    """
    Carrega CSVs do HD externo em tabelas Iceberg via PyIceberg na branch Nessie.

    Parâmetros (injetados pelo factory a partir do YAML load_csv):
        source_mount:  Caminho do HD no container (ex: /mnt/hd_rfb).
        tables:        Lista de dicts com file_pattern, target_schema, target_table.
        chunk_size:    Linhas por Parquet gerado (padrão: 500_000).
        encoding:      Encoding dos CSVs (padrão: latin-1).
        separator:     Separador de campos (padrão: ;).
    """
    ti = context.get("ti")
    branch_name = ti.xcom_pull(task_ids="create_nessie_branch") if ti else None

    if not branch_name:
        raise RuntimeError(
            "load_csv_to_iceberg requer branching habilitado. "
            "Nenhuma branch encontrada via XCom de 'create_nessie_branch'."
        )

    s3_conn = BaseHook.get_connection("minio_s3_connection")
    catalog = _catalog(branch_name, s3_conn)

    print(f"[rfb_csv_loader] Branch: {branch_name}")
    print(f"[rfb_csv_loader] Fonte:  {source_mount}")

    for table_cfg in tables:
        file_pattern = table_cfg["file_pattern"]
        target_schema = table_cfg["target_schema"]
        target_table = table_cfg["target_table"]

        _processar_tabela(
            catalog=catalog,
            source_mount=source_mount,
            file_pattern=file_pattern,
            target_schema=target_schema,
            target_table=target_table,
            chunk_size=chunk_size,
            encoding=encoding,
            separator=separator,
            branch_name=branch_name,
        )

    print("[rfb_csv_loader] Carga concluída para todas as tabelas.")


def _processar_tabela(
    catalog: RestCatalog,
    source_mount: str,
    file_pattern: str,
    target_schema: str,
    target_table: str,
    chunk_size: int,
    encoding: str,
    separator: str,
    branch_name: str,
):
    """Localiza os CSVs, lê em chunks e appenda na tabela Iceberg da branch."""

    # Resolve arquivos no HD que correspondem ao padrão
    padrao_glob = os.path.join(source_mount, "**", file_pattern)
    arquivos = sorted(glob.glob(padrao_glob, recursive=True))

    if not arquivos:
        # Tenta também no nível raiz do mount (sem subdiretórios)
        padrao_glob_flat = os.path.join(source_mount, file_pattern)
        arquivos = sorted(glob.glob(padrao_glob_flat))

    if not arquivos:
        raise FileNotFoundError(
            f"Nenhum arquivo encontrado para o padrão '{file_pattern}' "
            f"em '{source_mount}'. "
            f"Verifique se o HD está montado e os arquivos foram extraídos."
        )

    print(f"\n[{target_table}] {len(arquivos)} arquivo(s) encontrado(s).")

    colunas = _resolver_colunas(file_pattern)
    arrow_schema = _arrow_schema(colunas)   # schema explícito — evita pa.null()
    iceberg_table = catalog.load_table(f"{target_schema}.{target_table}")
    iceberg_table = _garantir_codec(iceberg_table, catalog, target_schema, target_table)

    for arquivo in arquivos:
        nome_arquivo = os.path.basename(arquivo)
        tamanho_mb = os.path.getsize(arquivo) / (1024 ** 2)
        print(f"  [{target_table}] Lendo {nome_arquivo} ({tamanho_mb:.1f} MB)...")

        total_linhas = 0
        num_chunk = 0

        reader = pd.read_csv(
            arquivo,
            sep=separator,
            encoding=encoding,
            header=None,
            names=colunas,
            dtype=str,           # Bronze: tudo como string — sem coerção de tipo aqui
            chunksize=chunk_size,
            on_bad_lines="warn", # Loga linhas malformadas sem interromper a carga
            engine="python",     # Parser Python: mais lento que o C mas imune ao
                                 # "Buffer overflow" nos arquivos brutos da RFB
        )

        for chunk_df in reader:
            num_chunk += 1

            # Remove linhas completamente vazias
            chunk_df = chunk_df.dropna(how="all")

            # Adiciona data_extracao como primeira coluna
            chunk_df.insert(0, "data_extracao", datetime.now(timezone.utc))

            # Schema explícito: garante pa.string() mesmo em colunas all-null
            arrow_table = pa.Table.from_pandas(
                chunk_df, schema=arrow_schema, preserve_index=False
            )
            _append_com_retry(iceberg_table, arrow_table)

            total_linhas += len(chunk_df)
            print(
                f"    chunk {num_chunk}: {len(chunk_df):,} linhas "
                f"(total acumulado: {total_linhas:,})"
            )

        print(f"  [{target_table}] {nome_arquivo}: {total_linhas:,} linhas carregadas.")

    print(f"[{target_table}] Tabela concluída na branch '{branch_name}'.")
