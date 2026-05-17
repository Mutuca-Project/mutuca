FROM apache/airflow:2.10.4-python3.11

USER root
# Instalação de pacotes do sistema
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

USER airflow

# Copia o arquivo de requisitos
COPY requirements.txt /requirements.txt

# Instala apenas as versões de bibliotecas compatíveis com a versão do Aiflow
RUN pip install --no-cache-dir -r /requirements.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.10.4/constraints-3.11.txt"

COPY entrypoint.sh /entrypoint.sh
USER root
RUN chmod +x /entrypoint.sh
USER airflow

# 3. Define o script como comando padrão
ENTRYPOINT ["/entrypoint.sh"]
