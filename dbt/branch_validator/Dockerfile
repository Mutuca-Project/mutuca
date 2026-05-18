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

# O projeto dbt é baked-in na imagem em tempo de build.
# COPY depois de WORKDIR copia dbt_project.yml, profiles.yml e models/ para dentro
# da imagem — sem volumes em runtime (DockerOperator não monta o projeto).
# DBT_PROFILES_DIR aponta para o WORKDIR para que o dbt encontre o profiles.yml
# sem precisar de --profiles-dir explícito no comando.
WORKDIR /dbt/branch_validator
COPY . .
ENV DBT_PROFILES_DIR=/dbt/branch_validator

# Ponto de entrada flexível:
# - Em produção (DockerOperator): CMD = ["test", "--target", "branch_validation", ...]
# - Na POC manual: CMD = ["python", "poc_duckdb_iceberg.py"]
ENTRYPOINT []
CMD ["dbt", "--help"]
