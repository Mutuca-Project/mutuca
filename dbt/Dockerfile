FROM python:3.10-slim

# Instalar git e dbt-trino
RUN apt-get update && apt-get install -y git && apt-get clean
RUN pip install --no-cache-dir dbt-trino

# Configurar diretório
WORKDIR /app

# Copiar projeto dbt
COPY ./lakehouse /app/lakehouse
COPY ./lakehouse/profiles.yml /root/.dbt/profiles.yml

WORKDIR /app/lakehouse

# Instalar dependências do dbt (se houver packages.yml)
RUN dbt deps

# Comando padrão (pode ser sobrescrito pelo Airflow)
ENTRYPOINT ["dbt"]
