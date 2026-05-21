# Como testar o pipeline `ingestao_rfb_cnpj`

## Visão geral

O teste é feito em **3 etapas** antes de soltar a carga completa:

1. Gerar CSVs de amostra no HD (sem esperar o download terminar)
2. Criar as tabelas no Trino
3. Disparar o DAG e verificar os dados

---

## Etapa 1 — Gerar CSVs de amostra para teste

Execute no terminal do host (fora do Docker). Ajuste o caminho para o HD:

```bash
# Defina o diretório alvo — mesmo valor que RFB_CNPJ_HD_PATH no .env
HD_PATH="/media/datafixer/<UUID-do-HD>/rfb_cnpj"
mkdir -p "$HD_PATH"

# Empresas (7 colunas, sem header, latin-1, separador ";")
python3 - <<'EOF'
import csv, random, string

caminho = f"{HD_PATH}/Empresas0.csv"
with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        cnpj = str(random.randint(10000000, 99999999))
        writer.writerow([
            cnpj,                          # cnpj_basico
            f"EMPRESA TESTE {i} LTDA",     # razao_social
            "2062",                        # natureza_juridica (Ltda)
            "49",                          # qualificacao_responsavel
            f"{random.randint(0,1000000)},00",  # capital_social
            "05",                          # porte_empresa
            "",                            # ente_federativo_responsavel
        ])
print(f"Criado: {caminho}")
EOF

# Estabelecimentos (30 colunas)
python3 - <<'EOF'
import csv, random

caminho = f"{HD_PATH}/Estabelecimentos0.csv"
with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        cnpj = str(random.randint(10000000, 99999999))
        # Alterna entre CNAE religioso e outros para testar o filtro Silver
        cnae = "9491000" if i % 5 == 0 else str(random.randint(1000000, 9999999))
        ufs = ["PE", "BA", "CE", "PB", "AL"]
        writer.writerow([
            cnpj, "0001", "00",           # basico, ordem, dv
            "1",                           # matriz
            f"FANTASIA {i}",               # nome_fantasia
            "2",                           # situacao_cadastral (Ativa)
            "20230101",                    # data_situacao
            "00",                          # motivo
            "", "", "20200101",            # cidade_ext, pais, data_inicio
            cnae,                          # cnae_principal ← crítico
            "",                            # cnae_secundaria
            "RUA", f"LOGRADOURO {i}", str(i), "", "BAIRRO",
            f"{random.randint(10000,99999):05d}-{random.randint(100,999)}",
            random.choice(ufs),
            str(random.randint(1000, 9999)),  # municipio
            "81", str(random.randint(30000000, 39999999)),
            "", "", "", "", "",             # ddd2, tel2, ddd_fax, fax, email
            "", "",                        # situacao_especial, data_especial
        ])
print(f"Criado: {caminho}")
EOF

# Socios (11 colunas)
python3 - <<'EOF'
import csv, random

caminho = f"{HD_PATH}/Socios0.csv"
nomes = ["JOAO DA SILVA", "MARIA SANTOS", "PASTOR JOSE FERREIRA", "BISPO ANTONIO"]
with open(caminho, "w", encoding="latin-1", newline="") as f:
    writer = csv.writer(f, delimiter=";")
    for i in range(1000):
        cnpj = str(random.randint(10000000, 99999999))
        writer.writerow([
            cnpj,                          # cnpj_basico
            "2",                           # identificador_socio (PF)
            random.choice(nomes),          # nome_socio
            f"***{random.randint(100,999)}***",  # cpf mascarado
            "49",                          # qualificacao
            "20200101",                    # data_entrada
            "105",                         # pais (Brasil)
            "", "",                        # representante, nome_rep
            "00",                          # qualificacao_rep
            "5",                           # faixa_etaria (41-50 anos)
        ])
print(f"Criado: {caminho}")
EOF
```

---

## Etapa 2 — Configurar o `.env` e reiniciar o Airflow

Adicione ao seu `.env` (se ainda não estiver):

```bash
RFB_CNPJ_HD_PATH=/media/datafixer/<UUID-do-HD>/rfb_cnpj
```

Reinicie o Airflow para o novo mount ser aplicado:

```bash
docker compose up -d --no-deps airflow
```

Verifique se o mount foi criado corretamente:

```bash
docker exec lakehouse-airflow ls /mnt/hd_rfb
# Deve listar: Empresas0.csv  Estabelecimentos0.csv  Socios0.csv
```

---

## Etapa 3 — Criar as tabelas no Trino

Conecte ao Trino e execute o DDL:

```bash
# Via CLI do container
docker exec -it lakehouse-trino trino

# Ou via trino CLI local apontando para localhost:8080
```

Cole o conteúdo de `sql/create_tables_rfb_cnpj.sql` e execute.

Confirme:

```sql
SHOW TABLES FROM iceberg.bronze LIKE 'rfb_cnpj%';
-- Deve retornar 3 linhas: rfb_cnpj_empresas, rfb_cnpj_estabelecimentos, rfb_cnpj_socios
```

---

## Etapa 4 — Disparar o DAG e monitorar

No Airflow UI (http://localhost:8081):

1. Ative o DAG `ingestao_rfb_cnpj` (toggle à esquerda)
2. Clique em **Trigger DAG** (ícone play)
3. Acompanhe o grafo de execução — a sequência esperada é:

```
create_nessie_branch
        │
        ▼
build_dbt_validator
        │
        ▼
load_csv_to_iceberg          ← lê os 3 CSVs, ~3000 linhas de teste
        │
        ▼
dbt_test_branch              ← valida not_null em cnpj_basico e data_extracao
        │
        ▼
merge_to_main
        │
        ▼
delete_branch
```

Tempo esperado para amostra de teste: **2–5 minutos**.

---

## Etapa 5 — Verificar os dados no Trino

```sql
-- Contagem por tabela
SELECT 'empresas' AS tabela, COUNT(*) AS linhas
FROM iceberg.bronze.rfb_cnpj_empresas
UNION ALL
SELECT 'estabelecimentos', COUNT(*)
FROM iceberg.bronze.rfb_cnpj_estabelecimentos
UNION ALL
SELECT 'socios', COUNT(*)
FROM iceberg.bronze.rfb_cnpj_socios;
-- Esperado: ~1000 linhas por tabela

-- Verificar coluna data_extracao (prova de cadeia de custódia)
SELECT data_extracao, cnpj_basico, razao_social
FROM iceberg.bronze.rfb_cnpj_empresas
LIMIT 5;

-- Antevisão do filtro Silver (CNAE religioso — será aplicado no dbt)
SELECT cnpj_basico, cnae_fiscal_principal, uf, municipio
FROM iceberg.bronze.rfb_cnpj_estabelecimentos
WHERE cnae_fiscal_principal = '9491000'
LIMIT 10;
```

---

## O que fazer se algo falhar

**`FileNotFoundError` no load_csv_to_iceberg:** O mount não está funcionando ou o padrão de arquivo
não bate.

```bash
docker exec lakehouse-airflow ls /mnt/hd_rfb
# Se vazio ou erro: checar RFB_CNPJ_HD_PATH no .env e reiniciar o Airflow
```

**`dbt_test_branch` falha:** Alguma linha tem `cnpj_basico` ou `data_extracao` nulo. Verificar o CSV
de amostra ou o log do Airflow para identificar o arquivo problemático. O comportamento correto é: a
branch é deletada sem contaminar `main`.

**Memória no Airflow estourada:** Reduzir `chunk_size` no YAML de 500000 para 200000 e retentar.

---

## Próximo passo após teste aprovado

Quando o download de 2023 estiver completo no HD:

1. Confirmar que todos os diretórios de 2023 estão presentes:
   ```bash
   ls $RFB_CNPJ_HD_PATH | head -20
   ```
2. Disparar o DAG normalmente — ele processará todos os arquivos encontrados.
3. A carga completa de 2023 pode levar várias horas. Monitorar memória do Airflow:
   ```bash
   docker stats lakehouse-airflow --no-stream
   ```
