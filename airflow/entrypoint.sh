#!/bin/bash
set -e

echo ">> Iniciando Setup do Airflow..."

# 1. Garantir que o Banco de Dados esteja atualizado
echo ">> Rodando Migrations..."
airflow db migrate

# 2. Configurar Usuário Admin (Estratégia: Deletar e Recriar)
# Isso garante que a senha do .env seja aplicada, ignorando estados anteriores.
echo ">> Configurando Usuário Admin..."

# Tenta deletar o usuário para limpar resquícios (ignora erro se não existir)
airflow users delete --username "$AIRFLOW_ADMIN_USER" || true

# Cria o usuário do zero com a senha correta
airflow users create \
    --username "$AIRFLOW_ADMIN_USER" \
    --password "$AIRFLOW_ADMIN_PASSWORD" \
    --firstname "Admin" \
    --lastname "User" \
    --role "Admin" \
    --email "$AIRFLOW_ADMIN_EMAIL"

# 3. Iniciar Scheduler em Background
echo ">> Iniciando Scheduler..."
airflow scheduler &

# 4. Iniciar Webserver em Foreground
echo ">> Iniciando Webserver..."
exec airflow webserver
