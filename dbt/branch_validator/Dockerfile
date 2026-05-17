FROM python:3.11-slim

# Dependências de sistema mínimas
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# dbt-duckdb carrega dbt-core e duckdb como dependências — deixamos o pip
# resolver as versões compatíveis entre si para evitar conflitos silenciosos.
# pyiceberg[pyarrow,s3] é pinado à mesma versão do container Airflow (issue #56)
# para garantir que o mecanismo de leitura em branch seja idêntico.
#
# NOTA: dbt-duckdb <1.8 usa duckdb <1.0; dbt-duckdb >=1.8 usa duckdb >=1.0.
# Não pinar duckdb separadamente — deixar o pip escolher a versão compatível.
RUN pip install --no-cache-dir \
    "dbt-duckdb>=1.8,<2.0" \
    "pyiceberg[pyarrow,s3]==0.11.1"

# O projeto dbt é montado em tempo de execução pelo DockerOperator.
# O profiles.yml vem junto com o projeto montado.
WORKDIR /dbt/branch_validator

# Ponto de entrada flexível:
# - Em produção (DockerOperator): CMD = ["test", "--target", "branch_validation", ...]
# - Na POC manual: CMD = ["python", "poc_duckdb_iceberg.py"]
ENTRYPOINT []
CMD ["dbt", "--help"]
