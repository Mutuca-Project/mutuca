# 🦟 Mutuca Platform (POC)
### Arquitetura de Data Lakehouse para Jornalismo de Dados e Análise Cívica

> **A transparência pública não é estática; os dados mudam, somem e se transformam. A infraestrutura precisa lembrar de tudo.**

---

## 📖 Sobre o Projeto

O **Mutuca** é uma Prova de Conceito (POC) de uma plataforma de dados moderna, open-source e agnóstica a nuvem (cloud-agnostic). Ele foi pensando e desenhado seguindo padrões de arquitetura e ferramentas consolidadas com foco especificamente para atender às necessidades de **redações independêntes de jornalismo investigativo, observatórios sociais e pesquisadores cívicos**.

No jornalismo de dados, por exemplo, enfrentamos desafios técnicos de naturezas distintas, mas que envolvem:
1.  **Volatilidade:** Dados em portais de transparência mudam retroativamente sem aviso.
2.  **Reprodutibilidade:** Uma reportagem baseada em dados precisa ser auditável e reproduzível meses depois.
3.  **Custo:** Redações independentes não podem arcar com faturas imprevisíveis e opacas de Big Techs (AWS, GCP).

O Mutuca resolve isso implementando uma arquitetura **Lakehouse** com **Versionamento de Dados (Git-like)**, rodando inteiramente em containers, capaz de operar em um servidor local acessível (commodity hardware).

## 🏗 Princípios Arquiteturais

1.  **Soberania e Baixo Custo:** A arquitetura não depende de serviços gerenciados proprietários. Tudo roda sobre Linux e Docker.
2.  **Auditabilidade por Design:** O projeto utiliza **Nessie + Apache Iceberg**. Isso nos permite "viajar no tempo" nos dados de maneira rápida e padronizada. Por exemplo, podemos provar qual era o valor de um contrato público no dia exato da publicação da matéria, mesmo que o governo (ou entidade pública) altere o dado no dia seguinte.
3.  **Arquitetura Medallion (refinamento):** Um padrão de design de dados para Lakehouse, popularizado pelo Databricks, que abstrai o armazenamento em três camadas de refinamento: **Bronze:** Dado bruto, exatamente como coletado (Histórico imutável).
    * **Silver:** Dado limpo, deduplicado, tipado e catalogado.
    * **Gold:** Dados agregados prontos para visualização e reportagem.
4.  **Monorepo Modular:** Infraestrutura centralizada, ingestão e transformação em um único repositório para facilitar a visão holística e o deploy, mas mantendo a separação lógica de responsabilidades.

## 🧩 Visão Geral da Arquitetura

O Mutuca é composto por cinco pilares fundamentais pensados como um departamentos de uma redação jornalística. Cada um possui sua própria documentação detalhada:

### 1. [O repórter de campo (Scrapy)](./scrapy/README.md)
* **Módulo:** Ingestão
* **Função:** Spiders Python especializados navegam em portais de transparência, diários oficiais e APIs, extraindo dados estruturados e não estruturados para armazenando em um Data Lake.

### 2. [Arquivo Morto & O Cartório (Nessie & MinIO)](./infrastructure/nessie/README.md)
* **Módulo:** Storage & Catalog
* **Função:** O MinIO atua como Object Storage. O Nessie gerencia o catálogo do Apache Iceberg, permitindo branches, commits e tags nos dados, assim como fazemos com código no Git. O MinIO guarda os arquivos (o cofre). O Nessie registra o histórico (o livro de registros). Se um dado for apagado, o Nessie sabe exatamente como recuperá-lo viajando no tempo (Time Travel).

### 3. [A mesa de investigação (Trino)](./infrastructure/trino/README.md)
* **Módulo:** Query Engine 
* **Função:** Como o motor de consulta SQL distribuído massivamente paralelo, o Trino é quem otimiza as consultas feitas aos dados armazenados no Lakehouse. Em outras palávras, o "cérebro". Permite cruzar milhões de linhas de contratos, doações e sócios, por exemplo, usando SQL sem precisar baixar planilhas gigantes para o Excel.

### 4. [Checagem de Fatos (dbt)](./dbt/README.md)
* **Módulo:** Transformação & Qualidade 
* **Função:** Aplica regras de negócio, limpeza, deduplicação e testes de qualidade (Data Quality) usando SQL. Transforma dados brutos em dados confiáveis e seguros para apuração jornalística.

### 5. [Editor de pauta (Airflow)](./airflow/README.md)
* **Módulo:** Orquestração. 
* **Função:** Define a hora da coleta, garante a sequência lógica (Coletar -> Transformar -> Testar) e avisa se algo der errado.

---
## Guia de Início Rápido (Quickstart)

Pré-requisitos Técnicos

- Docker & Docker Compose (V2): O motor da infraestrutura.
- Python 3.11+: Linguagem base.
- Hardware: Mínimo de 16GB RAM (O Trino e o Airflow são intensivos em memória).
- Sistema Operacional: Linux ou WSL2 (Windows).

### Passo 1: Clone e Configuração

```bash
git clone git@github.com:datafixerbr/mutuca-platform.git
cd mutuca-platform

# Crie o arquivo de variáveis de ambiente
cp env_example .env

# DICA: Edite o .env se precisar ajustar senhas ou portas

```

### Passo 2: Ambientes Virtuais (Venvs)

⚠️ Atenção: Um erro comum é tentar instalar tudo no mesmo Python. Não faça isso. Cada componente (Scrapy, dbt, Airflow) tem dependências conflitantes. Crie ambientes isolados para desenvolvimento:

#### Para desenvolver os Spiders


```bash
uv venv ./scrapy/.venv
source scrapy/.venv/bin/activate && uv sync --project scrapy && deactivate
```


#### Para desenvolver Transformações SQL

```bash

uv venv ./dbt/.venv
source ./dbt/.venv/bin/activate && uv sync --project dbt && deactivate

```

#### Para operações manuais de branches Nessie (diagnóstico de infraestrutura)

Este venv é usado apenas no host, para inspecionar e manipular branches diretamente no terminal,
sem precisar do Airflow. Em produção, o `pynessie` roda dentro do container Airflow.

```bash

uv venv ./infrastructure/nessie/.venv
source infrastructure/nessie/.venv/bin/activate && uv sync --project infrastructure/nessie && deactivate

```

O ponto de entrada CLI é sempre `airflow/dags/shared/nessie_client.py`:

```bash
source infrastructure/nessie/.venv/bin/activate

python airflow/dags/shared/nessie_client.py hash main          # ver hash HEAD da main
python airflow/dags/shared/nessie_client.py create minha-branch
python airflow/dags/shared/nessie_client.py merge  minha-branch
python airflow/dags/shared/nessie_client.py delete minha-branch
```

#### Para testar DAGs localmente (opcional, pois o Docker resolve isso)

```

uv venv ./airflow/.venv
source ./airflow/.venv/bin/activate && uv sync --project airflow && deactivate

```

### Passo 3: Subindo a Infraestrutura

```bash
# Sobe todos os serviços em modo "detached" (background)
docker compose up -d

```

### Passo 4: Check liste de validação  

Antes de começar a desenvolver pipelines, garanta que todos os "departamentos da redação" estão de pé e funcionais. Como engenheiros jornalistas, o terminal é nossa mesa de trabalho. Abaixo está uma lista de validação da infraestrutura e comandos úteis para monitorar e consertar a casa.

1. Status dos Containers: Execute: `docker compose ps`

- [ ] Trino: Deve estar (healthy). Se estiver starting por muito tempo, ele pode estar sem memória.
- [ ] MinIO: Deve estar (healthy).
- [ ] Nessie: Deve estar (healthy) ou Up.
- [ ] Airflow-Webserver: Deve estar (healthy).

2. Teste de Acesso (Interfaces):

- [ ] Consigo abrir o MinIO (localhost:9001) e logar?
- [ ] Consigo abrir o Airflow (localhost:8081) e ver as DAGs?
- [ ] O bucket bronze existe no MinIO? (Se não, crie-o manualmente ou via script).

3. Teste de Conexão SQL:

- [ ] Abra o DBeaver (ou outro cliente SQL). Conecte no Trino (localhost:8080).
- [ ] Execute: SHOW CATALOGS;. O resultado deve incluir `iceberg`.
- [ ] Execute: `SELECT * FROM iceberg.information_schema.tables`;. Não deve dar erro.

4. Cinto de utilidades Docker:
- "O que está acontecendo agora?" (Logs em tempo real) Se uma tarefa falhar ou o banco travar, o log conta a história.

```bash
# Ver logs de todos os serviços (caótico)
docker compose logs -f

# Ver logs de um serviço específico (recomendado)
docker compose logs -f airflow-scheduler
docker compose logs -f trino

```

- "Quem está comendo minha memória?" (Resource Monitor) Essencial para quem roda em notebooks com 16GB de RAM. Se o computador ficar lento, rode isso.

```bash
docker stats

# Olho vivo: O trino e o nessie (java) são os maiores consumidores. Se o Trino passar de 6GB, ele periga travar o sistema.

```

- "Como entrar na Matrix" (Shell dentro do Container): Você pode precisar entrar no container para instalar uma lib na mão ou testar conectividade (ping, curl).

```bash
# Entrar no Airflow
docker compose exec airflow bash
# Entrar no Trino (para rodar CLI nativo)
docker compose exec trino trino

```

- "A Bomba Atômica" (Reset Total + Correção de Metadados Zumbis) Use este comando quando tiver problemas de inconsistência (ex: Trino diz que tabela existe, mas arquivo sumiu do MinIO). 

⚠️ Aviso: Isso apaga TODOS os dados e o histórico do Nessie. A redação volta a ser uma folha em branco.

```bash
# O flag '-v' remove os volumes (discos virtuais)
docker compose down -v

# Subir tudo limpo novamente
docker compose up -d

```

- "Faxina Geral" (Liberar Espaço em Disco) O Docker acumula imagens antigas e cache de build (especialmente com nosso padrão DooD). Se seu HD lotar:

```bash
# Remove containers parados, redes não usadas e imagens "dangling"
docker system prune -f
```

3. O "Ping" da redação 

Se os containers estão de pé (`Up`), mas os dados não fluem, o problema (como diria aquele seu amigo da TI) geralmente é o "cabo de rede".

Cada componente precisa se reconhecer. Para que isso ocorra, eles precisam estar na mesma rede. No arquivo `docker-compose.yml`, podemos ver que essa rede se chama `lakehouse-net`:

```bash
# no fim do arquivo docker-compose.yml
....

networks:
  lakehouse-net:
    driver: bridge
```

Use os comando abaixo para simular a visão que um componente tem do outro:

1. Testar o Airflow -> Docker (DooD Check)

```bash 
# Execute dentro da pasta do projeto 
docker compose exec airflow docker ps

# Sucesso: Lista de containers rodando (Trino, MinIO, etc)
# Falha: "docker: command not found" ou "permission denied"
# Solução: Verifique se o volume /var/run/docker.sock está montado no docker-compose.yml

```

2. Testar Trino → MinIO (Acesso aos Arquivos)

```bash
# O Trino tenta acessar o healthcheck do MinIO
docker compose exec trino curl -v http://minio:9000/minio/health/live

# Sucesso: HTTP/1.1 200 OK
# Falha: "Could not resolve host" ou "Connection refused".
# Solução: Verifique se ambos estão na rede 'lakehouse-net'.
```


3. Testar Trino → Nessie (Acesso ao Catálogo)

O Trino precisa consultar o Nessie para saber onde estão as tabelas.

```bash
docker compose exec trino curl -v http://nessie:19120/api/v2/config

# Sucesso: Retorna um JSON com configs do Nessie.
# Falha: Timeout ou 404.
# Solução: Verifique se ambos estão na rede 'lakehouse-net'.
```

4. Testar Resolução de Nomes (DNS Interno)

É possível que o Airflow não ache o Trino por não conseguir resolver o nome "trino". Teste a "lista telefônica" interna do Docker:

```bash
docker compose exec airflow python3 -c "import socket; print(socket.gethostbyname('trino'))"

# Pergunta ao container do Airflow: "Quem é o Trino?"
# Sucesso: Imprime um IP (ex: 172.18.0.4)
# Falha: "gaierror: [Errno -2] Name or service not known"
```

5. Testar Credenciais S3 (Python Script)

Se o Scrapy falha ao salvar, valide se as chaves no .env funcionam de verdade. Crie um arquivo `teste_s3.py` temporário:

```python

# Crie este arquivo na raiz do repositório e rode com: python3 teste_s3.py
import os
import boto3
from dotenv import load_dotenv

load_dotenv()

s3 = boto3.client(
    's3',
    endpoint_url='http://localhost:9000', # Atenção: Localhost pois você roda do host
    aws_access_key_id=os.getenv('MINIO_ROOT_USER'),
    aws_secret_access_key=os.getenv('MINIO_ROOT_PASSWORD')
)

try:
    print("Buckets:", s3.list_buckets()['Buckets'])
    print("✅ Conexão S3 OK!")
except Exception as e:
    print(f"❌ Erro S3: {e}")

```
---

