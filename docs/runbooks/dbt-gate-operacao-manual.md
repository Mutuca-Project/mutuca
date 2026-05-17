# Runbook — Operação Manual do Gate dbt Pré-Merge (ADR 008)

**Propósito:** Rodar o gate de validação `dbt test` manualmente contra uma branch Nessie
específica, sem depender da execução do Airflow. Útil para:
- Investigar uma falha do gate em produção
- Validar dados de uma branch órfã antes de fazer merge manual
- Testar um novo conjunto de testes no `sources.yml` antes de integrar ao pipeline

---

## Pré-condições

```bash
# 1. Confirmar que a stack está rodando
docker compose ps

# 2. Confirmar que a branch existe no Nessie
curl -s http://localhost:19120/api/v2/trees \
  | jq '.references[] | select(.name | startswith("ingest_")) | {name, hash: .hash}'

# 3. Confirmar que a imagem do validador existe
docker images lakehouse-dbt-validator:latest
```

Se a imagem não existir, construa-a:
```bash
docker build -t lakehouse-dbt-validator:latest dbt/branch_validator/
```

---

## Executar o gate manualmente

Substitua `<NOME_DA_BRANCH>` pelo nome real da branch (ex: `ingest_lattes_ssd_20260516_143022`):

```bash
BRANCH_NAME="<NOME_DA_BRANCH>"

docker run --rm \
  --network mutuca-lakehouse_lakehouse-net \
  -e NESSIE_ICEBERG_ENDPOINT="http://lakehouse-nessie:19120/iceberg/" \
  -e NESSIE_BRANCH="${BRANCH_NAME}" \
  -e MINIO_ENDPOINT="http://lakehouse-minio:9000" \
  -e MINIO_ACCESS_KEY="minioadmin" \
  -e MINIO_SECRET_KEY="minioadmin" \
  lakehouse-dbt-validator:latest \
  dbt test --target branch_validation --select source:bronze
```

**Saída esperada (sucesso):**

```
Running with dbt=1.11.10
...
Done. PASS=3 WARN=1 ERROR=0 FAIL=0 SKIPPED=0 TOTAL=4
Finished running 4 tests in 0 hours 5 minutes 37.97 seconds (337.97s).
```

**Saída esperada (falha — dados ruins):**

```
...
Done. PASS=2 WARN=0 ERROR=1 FAIL=1 SKIPPED=0 TOTAL=4
Finished running 4 tests in ...
```

Exit code será `1` em caso de ERROR ou FAIL. O `docker run --rm` encerra o container automaticamente.

---

## Rodar apenas um teste específico

Para um diagnóstico mais rápido, selecione apenas o teste problemático:

```bash
# Apenas o teste not_null em id_lattes
docker run --rm \
  --network mutuca-lakehouse_lakehouse-net \
  -e NESSIE_ICEBERG_ENDPOINT="http://lakehouse-nessie:19120/iceberg/" \
  -e NESSIE_BRANCH="${BRANCH_NAME}" \
  -e MINIO_ENDPOINT="http://lakehouse-minio:9000" \
  -e MINIO_ACCESS_KEY="minioadmin" \
  -e MINIO_SECRET_KEY="minioadmin" \
  lakehouse-dbt-validator:latest \
  dbt test --target branch_validation --select "source:bronze,test_name:not_null"
```

---

## Inspecionar os dados da branch via Python (diagnóstico direto)

Para entender _por que_ um teste falhou, inspecione os dados diretamente via PyIceberg:

```bash
# Abrir shell no container do validador
docker run --rm -it \
  --network mutuca-lakehouse_lakehouse-net \
  -e NESSIE_ICEBERG_ENDPOINT="http://lakehouse-nessie:19120/iceberg/" \
  -e NESSIE_BRANCH="${BRANCH_NAME}" \
  -e MINIO_ENDPOINT="http://lakehouse-minio:9000" \
  -e MINIO_ACCESS_KEY="minioadmin" \
  -e MINIO_SECRET_KEY="minioadmin" \
  --entrypoint bash \
  lakehouse-dbt-validator:latest
```

Dentro do container:

```python
python3 << 'EOF'
import os
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "nessie_branch",
    type="rest",
    uri=os.environ["NESSIE_ICEBERG_ENDPOINT"],
    prefix=os.environ["NESSIE_BRANCH"],
    **{
        "s3.endpoint": os.environ["MINIO_ENDPOINT"],
        "s3.access-key-id": os.environ["MINIO_ACCESS_KEY"],
        "s3.secret-access-key": os.environ["MINIO_SECRET_KEY"],
        "s3.path-style-access": "true",
    }
)

table = catalog.load_table("bronze.lattes_raw")
df = table.scan().to_arrow().to_pandas()

print(f"Total de linhas: {len(df)}")
print(f"\nNulos por coluna:")
print(df.isnull().sum())
print(f"\nDuplicatas em id_lattes: {df['id_lattes'].duplicated().sum()}")
print(f"\nAmostra:")
print(df.head())
EOF
```

---

## Fazer merge manual após validação bem-sucedida

Se o gate passou e você quer mergear a branch manualmente (sem re-executar o DAG):

```bash
# Usando o nessie_client.py (requer venv do Nessie ativo)
source infrastructure/nessie/.venv/bin/activate
python airflow/dags/shared/nessie_client.py merge "${BRANCH_NAME}"

# Verificar que o merge ocorreu (hash de main deve ter avançado)
python airflow/dags/shared/nessie_client.py hash main
```

---

## Deletar uma branch manualmente

Branches órfãs (de execuções que falharam sem cleanup) devem ser deletadas para não degradar
a performance do catálogo:

```bash
source infrastructure/nessie/.venv/bin/activate

# Listar branches de ingestão existentes
python airflow/dags/shared/nessie_client.py hash main  # confirmar que main está ok antes

# Deletar a branch órfã
python airflow/dags/shared/nessie_client.py delete "${BRANCH_NAME}"
```

Para listar todas as branches diretamente via API:

```bash
curl -s http://localhost:19120/api/v2/trees \
  | jq '.references[] | select(.name | startswith("ingest_")) | .name'
```
