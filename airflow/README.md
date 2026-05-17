# 🌬 Módulo de Orquestração: Apache Airflow

> ** A notícia não espera. Então, não perca tempo gerenciando diferentes ferramentas na mão!"**

O Airflow é o coração pulsante da **Plataforma Mutuca**. Ele define a ordem lógica de execução de tarefas e gerencia as dependências entre os diferentes módulos.

## 📍 Papel na Arquitetura
Consulte a visão global em [../README.md](../README.md).

O Airflow não processa dados (quem faz isso é o Trino), ele processa **tarefas**.
Um pipeline típico no Mutuca segue esta DAG (Directed Acyclic Graph):

1.  **Start:** Início agendado (ex: todo dia às 02:00).
2.  **Branch Creation:** Cria uma branch no Nessie para isolar a ingestão do dia (`etl/2026-02-06`).
3.  **Ingestion (Scrapy):** Roda o container do Scrapy para baixar novos dados.
4.  **Transformation (dbt):** Aciona o dbt para limpar os dados novos.
5.  **Data Quality (Great Expectations):** Valida se os dados estão dentro dos padrões.
6.  **Merge/Publish:** Se tudo estiver correto, faz o merge da branch para a `main`.

## 🐳 Estratégia de Execução (Docker-outside-of-Docker)

Para manter o ambiente leve e segregado, utilizo o `DockerOperator`.
O Airflow não instala o Scrapy ou dbt no seu mesmo container. Ele ordena que o Docker do host suba containers efêmeros dessas ferramentas. Isso garante que conflitos de bibliotecas Python nunca aconteçam aumentando a confiabilidade no processo e, consequentemente, nos dados.

## 📂 Estrutura

```
airflow/
├── dags/              # Definição dos pipelines (Python)
├── plugins/           # Plugins customizados
└── Dockerfile         # Imagem customizada do Airflow
```

### ⚙️ Acessando a Interface

O Airflow está disponível em http://localhost:8081.
    - Usuário: admin
    - Senha: admin
