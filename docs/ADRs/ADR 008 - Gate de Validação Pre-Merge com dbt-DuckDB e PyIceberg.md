## Context

O ADR 007 estabeleceu o padrão de branching por execução via Nessie: cada ingestão abre uma branch
isolada e só faz merge para `main` após validação. O ADR 007 declarava o `dbt test` como o gate
de validação, mas deixava em aberto **como** esse gate seria implementado tecnicamente.

O problema central é que o motor SQL de produção — o Trino — não consegue apontar para uma branch
Nessie específica quando o catálogo usa `catalog.type=rest`. Tentativas de selecionar branch via
`session_properties` retornam `INVALID_SESSION_PROPERTY`. O Trino sempre lê `main`. Portanto,
rodar `dbt test` com o perfil Trino de produção (`dbt/lakehouse/profiles.yml`) não valida os dados
da branch de ingestão em andamento — ele validaria os dados que já estão em `main`, o que é
semanticamente incorreto e inútil como gate pré-merge.

A questão concreta que motivou este ADR foi: **qual motor SQL é capaz de conectar ao Nessie com
routing para uma branch específica, consumindo dados do MinIO via Iceberg REST catalog, sem exigir
um serviço adicional na stack?**

Dois candidatos foram investigados empiricamente (maio de 2026):

1. **DuckDB com extensão `httpfs` e `ATTACH ... (TYPE iceberg)`** — acesso nativo ao catálogo
   Nessie sem dependências Python adicionais.
2. **DuckDB via dbt-duckdb com plugin iceberg (PyIceberg como bridge)** — usa PyIceberg para
   abrir o catálogo e expõe as tabelas Arrow ao DuckDB via memória compartilhada.

---

## Investigation: O que foi testado e o que falhou

### Candidato 1: DuckDB nativo via ATTACH

O DuckDB suporta o protocolo Iceberg REST nativo via extensão `httpfs`. O comando:

```sql
ATTACH 'http://lakehouse-nessie:19120/iceberg' AS nessie_catalog (TYPE iceberg);
SHOW TABLES;
```

**Resultado:** Lista as tabelas corretamente (validado: `lattes_raw`, `quotes`, e demais tabelas
de `main`). A conectividade com o endpoint REST do Nessie funciona.

**Limitação crítica — routing de branch:**

```sql
-- Tentativa: adicionar branch ao endpoint
ATTACH 'http://lakehouse-nessie:19120/iceberg/main' AS nessie_catalog (TYPE iceberg);
SHOW TABLES;
-- Resultado: 0 tabelas — a extensão DuckDB não reconhece o sufixo de path como branch routing
```

O DuckDB nativo não suporta a semântica de `prefix` do protocolo Iceberg REST (RFC: o campo
`prefix` roteia todas as chamadas para `{uri}/{prefix}/v1/...`). Testou-se tanto o sufixo no
endpoint quanto parâmetros de query — nenhum funcionou.

**Limitação crítica — leitura de dados do MinIO:**

Mesmo para `main` (onde o routing funcionou pela ausência de sufixo), a leitura dos arquivos
Parquet falhou com erro 403 durante a resolução dos data files:

```
HTTP Error: HTTP GET error on 'http://lakehouse-minio:9000/warehouse/...' (403 Forbidden)
```

Duas abordagens de configuração S3 foram testadas:

```sql
-- Abordagem 1: CREATE SECRET
CREATE SECRET minio_secret (
    TYPE s3,
    KEY_ID 'minioadmin',
    SECRET 'minioadmin',
    ENDPOINT 'lakehouse-minio:9000',
    USE_SSL false,
    URL_STYLE path
);
-- Resultado: 403 persistente

-- Abordagem 2: SET global
SET s3_endpoint='lakehouse-minio:9000';
SET s3_access_key_id='minioadmin';
SET s3_secret_access_key='minioadmin';
SET s3_use_ssl=false;
SET s3_url_style='path';
-- Resultado: 403 persistente
```

A raiz do problema é que o DuckDB `httpfs` não usa o endpoint configurado para URLs que chegam
via metadata do catálogo Iceberg — ele tenta resolver `s3://` URIs via AWS SDK, que não tem acesso
ao MinIO local. O endpoint customizado não é propagado para a resolução de data files do catálogo.

**Conclusão sobre DuckDB nativo:** descartado por dois motivos independentes — (1) não suporta
branch routing via `prefix`, (2) não consegue ler data files do MinIO via catálogo Iceberg.

---

### Candidato 2: dbt-duckdb com plugin iceberg (PyIceberg bridge)

O `dbt-duckdb` suporta um sistema de plugins que permite registrar "relações virtuais" no DuckDB
a partir de fontes externas. O plugin `iceberg` usa PyIceberg para abrir o catálogo, escanear a
tabela, serializar para Apache Arrow em memória, e registrar como view DuckDB. O DuckDB então
opera sobre os dados Arrow sem nunca fazer chamadas S3 diretamente.

**Mecanismo de branch routing validado:**

O `RestCatalog` do PyIceberg aceita um parâmetro `prefix` que roteia todas as chamadas REST para
`{uri}/{prefix}/v1/...`. Isso é exatamente o mecanismo de branch routing do Nessie — o servidor
mapeia o prefixo para a branch correspondente:

```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog(
    "nessie_branch",
    type="rest",
    uri="http://lakehouse-nessie:19120/iceberg/",
    prefix="ingest_lattes_ssd_20260516_143022",   # ← branch name
    **{"s3.endpoint": "http://lakehouse-minio:9000",
       "s3.access-key-id": "minioadmin",
       "s3.secret-access-key": "minioadmin",
       "s3.path-style-access": "true"}
)
table = catalog.load_table("bronze.lattes_raw")
arrow_table = table.scan().to_arrow()   # 53.893 linhas validadas
```

**Resultado:** ✅ Funciona. PyIceberg usa `fsspec` com `s3fs` para resolver os data files —
respeitando o endpoint e credenciais customizadas passados nas propriedades do catálogo. O DuckDB
nativo falha exatamente aqui porque não usa o mesmo mecanismo de resolução de S3.

**Configuração do profiles.yml descoberta iterativamente:**

A estrutura correta do plugin no `profiles.yml` do `dbt-duckdb` não estava documentada para o
caso PyIceberg + Nessie. Ela foi descoberta por engenharia reversa do código-fonte do plugin
(`dbt/adapters/duckdb/plugins/iceberg.py`) e por iteração sobre erros. As armadilhas críticas:

| Erro encontrado | Causa | Solução |
|---|---|---|
| `No module named 'dbt_duckdb.plugins.iceberg'` | Nome de módulo errado | Usar `module: iceberg` (nome curto, resolvido pelo loader do plugin) |
| `'catalog' is a required argument` | Estrutura errada com chaves `catalog_name`/`catalog_type` | Usar estrutura flat: `catalog: <nome_string>` no mesmo nível que `type:`, `uri:`, etc. |
| `'dict' object has no attribute 'upper'` | `catalog` era um dict aninhado | `catalog` deve ser uma **string** (o nome do catálogo, primeiro arg posicional de `load_catalog()`) |

A assinatura real da função que o plugin chama é:
```python
pyiceberg.catalog.load_catalog(catalog, **config)
#                              ^ string  ^ todas as demais chaves do config
```

O `profiles.yml` correto e validado:

```yaml
branch_validator:
  target: branch_validation
  outputs:
    branch_validation:
      type: duckdb
      path: ':memory:'
      plugins:
        - module: iceberg          # ← nome curto (não dbt_duckdb.plugins.iceberg)
          alias: iceberg_branch
          config:
            catalog: nessie_branch  # ← STRING: nome do catálogo (arg posicional)
            type: rest              # ← propriedades PyIceberg no mesmo nível flat
            uri: "{{ env_var('NESSIE_ICEBERG_ENDPOINT') }}"
            prefix: "{{ env_var('NESSIE_BRANCH') }}"
            s3.endpoint: "{{ env_var('MINIO_ENDPOINT') }}"
            s3.access-key-id: "{{ env_var('MINIO_ACCESS_KEY') }}"
            s3.secret-access-key: "{{ env_var('MINIO_SECRET_KEY') }}"
            s3.path-style-access: "true"
```

**Resultado do `dbt test` validado empiricamente:**

```
Running with dbt=1.11.10
...
Completed with 1 warning:
Done. PASS=3 WARN=1 ERROR=0 FAIL=0 SKIPPED=0 TOTAL=4

Finished running 4 tests in 0 hours 5 minutes 37.97 seconds (337.97s).
```

Os 4 testes rodaram sobre 53.893 linhas da tabela `bronze.lattes_raw` na branch
`ingest_lattes_ssd_20260516_143022`. WARN foi `unique` em `id_lattes` (severidade configurada como
`warn`, não `error` — IDs duplicados são esperados em lotes de re-ingestão).

---

## Decision

Implementar o gate de validação pré-merge como um **container efêmero `lakehouse-dbt-validator`**,
executado via `DockerOperator` do Airflow (padrão DooD, já estabelecido no ADR 004), usando
`dbt-duckdb` com o plugin `iceberg` (PyIceberg bridge) para ler dados diretamente da branch Nessie
de ingestão antes do merge para `main`.

O container é construído a partir de `dbt/branch_validator/Dockerfile` com o código baked-in —
sem volumes em runtime, seguindo o mesmo princípio de imutabilidade dos containers Scrapy.

O nome da branch é passado via XCom do Airflow (task `create_nessie_branch`) como variável de
ambiente `NESSIE_BRANCH`, resolvida via template Jinja pelo DockerOperator:

```python
"NESSIE_BRANCH": "{{ ti.xcom_pull(task_ids='create_nessie_branch') }}"
```

O gate é **bloqueante**: se `dbt test` retornar exit code ≠ 0 (qualquer teste com `severity:
error` falhar), o `merge_to_main` é impedido. O `delete_branch` usa `TriggerRule.ALL_DONE` para
garantir limpeza em ambos os caminhos (sucesso e falha), conforme ADR 007.

O grafo de dependências completo para `branching: enabled: true`:

```
create_nessie_branch
    ├── setup_docker_env (build scrapy)    ─┐
    └── build_dbt_validator (parallel)     ─┤→ crawl_{spider}
                                                    │
                                              load_to_iceberg
                                                    │
                                             dbt_test_branch   ← gate: error bloqueia merge
                                                    │
                                              merge_to_main
                                                    │
                                          [increment_batch_offset]  ← apenas se offset_control declarado
                                                    │
                                              delete_branch (ALL_DONE — cleanup garantido)
```

Os builds de `lakehouse-scraper` e `lakehouse-dbt-validator` rodam em paralelo (ambos dependem de
`create_nessie_branch`, e `crawl_{spider}` espera ambos). Isso elimina o overhead do build do
validador do caminho crítico.

---

## Stack técnica do branch_validator

| Componente | Versão | Observação |
|---|---|---|
| `dbt-core` | 1.11.10 (resolvido por pip) | Instalado como dependência de `dbt-duckdb` |
| `dbt-duckdb` | 1.10.1 | Especificado como `>=1.8,<2.0` no Dockerfile |
| `DuckDB` | 1.5.2 (resolvido por pip) | Instalado como dependência de `dbt-duckdb` |
| `pyiceberg` | 0.11.1 | Especificado como `pyiceberg[pyarrow,s3]==0.11.1` |
| Imagem base | `python:3.11-slim` | Sem JVM, sem Spark — footprint mínimo |

**Por que não pinamos dbt-core e DuckDB?** O `pip` resolve automaticamente versões compatíveis a
partir do `dbt-duckdb` constraint. Pinagem explícita criaria rigidez desnecessária e risco de
conflito com futuras atualizações do `pyiceberg`. Se surgir instabilidade de versão, adicionamos
pins explícitos no Dockerfile.

**Por que `python:3.11-slim` e não a imagem oficial do dbt?** A imagem oficial do dbt (ghcr.io/
dbt-labs/dbt-duckdb) não inclui `pyiceberg[s3]` e teria que ser derivada de qualquer forma.
`python:3.11-slim` é mais previsível e compatível com o hardware de 16GB (sem camadas desnecessárias).

---

## Estrutura dos artefatos implementados

```
dbt/
└── branch_validator/
    ├── Dockerfile                        # Build da imagem lakehouse-dbt-validator:latest
    ├── profiles.yml                      # Único profiles.yml versionado no repo (usa env_var())
    ├── dbt_project.yml                   # name: branch_validator, sem seção models:
    ├── .gitignore                        # Exclui .user.yml e target/
    └── models/
        └── bronze/
            └── sources.yml               # Declaração das fontes + testes DQ por coluna
```

**Por que `profiles.yml` está no repositório?** O `profiles.yml` normalmente é ignorado pelo
`.gitignore` do dbt porque pode conter credenciais hardcoded. O `branch_validator/profiles.yml`
usa exclusivamente `env_var()` para qualquer dado sensível — sem exceções. Por isso, o
`.gitignore` raiz do `dbt/` tem uma exceção explícita:

```gitignore
# dbt/.gitignore
profiles.yml
!branch_validator/profiles.yml   ← excepcionado: usa apenas env_var(), sem credenciais
```

**Por que não há seção `models:` no `dbt_project.yml`?** O `branch_validator` é exclusivamente
um executor de testes em fontes — não tem modelos SQL. A seção `models:` vazia ou com caminhos
inexistentes gera warnings de "unused configuration path" no `dbt test`. Removê-la é o comportamento
correto para um projeto test-only.

---

## Declaração de fontes e testes (sources.yml)

O arquivo `models/bronze/sources.yml` centraliza a declaração das fontes Iceberg e os testes DQ:

```yaml
version: 2
sources:
  - name: bronze
    tables:
      - name: lattes_raw
        meta:
          plugin: iceberg_branch        # ← referencia o alias do plugin no profiles.yml
          table: bronze.lattes_raw      # ← namespace.tabela no catálogo Iceberg
        columns:
          - name: data_extracao
            tests:
              - not_null:
                  config:
                    severity: error     # ← dentro de config: (exigência do dbt >= 1.9)
          - name: id_lattes
            tests:
              - not_null:
                  config:
                    severity: error
              - unique:
                  config:
                    severity: warn      # ← warn: duplicatas esperadas em re-ingestões
          - name: nome
            tests:
              - not_null:
                  config:
                    severity: warn
```

**Armadilha de sintaxe crítica (dbt >= 1.9):** `severity` deve estar dentro do bloco `config:`.
Colocá-lo diretamente sob o nome do teste:

```yaml
# ERRADO (deprecado/erro em dbt >= 1.9)
- not_null:
    severity: error

# CORRETO
- not_null:
    config:
      severity: error
```

**Armadilha de declaração duplicada:** `sources.yml` e `schema.yml` não podem declarar a mesma
fonte `bronze`. Durante a implementação, coexistência dos dois arquivos gerou erro:
`Found two sources with name 'bronze_lattes_raw'`. Solução: consolidar tudo em `sources.yml`
e deletar `schema.yml`.

---

## Integração no factory.py (ADR 006)

O `factory.py` foi atualizado para gerar o gate `dbt_test_branch` como parte do grafo de
dependências quando `branching: enabled: true`. Pontos de integração relevantes:

**Build paralelo:**
```python
_BUILD_DBT_VALIDATOR_SCRIPT = """
echo "--- BUILD DBT VALIDATOR ---"
docker build -t lakehouse-dbt-validator:latest /opt/airflow/project/dbt/branch_validator
"""

build_dbt_validator = BashOperator(
    task_id="build_dbt_validator",
    bash_command=_BUILD_DBT_VALIDATOR_SCRIPT,
)

# Paralelo: scraper e validador são construídos simultaneamente
[setup_env, build_dbt_validator] >> run_scraper
```

**DockerOperator do gate:**
```python
dbt_test_task = DockerOperator(
    task_id="dbt_test_branch",
    image="lakehouse-dbt-validator:latest",
    container_name=f"dbt_validator_{dag_id}_ephemeral",
    api_version="auto",
    auto_remove="force",
    mount_tmp_dir=False,
    network_mode="mutuca-lakehouse_lakehouse-net",
    command=(
        "dbt test "
        "--target branch_validation "
        "--select source:bronze"
    ),
    environment={
        "NESSIE_ICEBERG_ENDPOINT": nessie_iceberg_endpoint,
        "NESSIE_BRANCH": "{{ ti.xcom_pull(task_ids='create_nessie_branch') }}",
        "MINIO_ENDPOINT": minio_endpoint,
        "MINIO_ACCESS_KEY": conn.login,
        "MINIO_SECRET_KEY": conn.password,
    },
    docker_url="unix://var/run/docker.sock",
)
```

**Grafo de dependências atualizado:**
```python
load_task >> dbt_test_task >> merge_task

# delete depende do último task do caminho de sucesso
# E de load_task diretamente (caminho de falha em dbt)
last_success_task >> delete_task
load_task >> delete_task         # ALL_DONE: cleanup mesmo se dbt falhar
```

O `last_success_task` é `merge_task` se não houver `offset_control`, ou `offset_task` se houver.
Isso garante que `increment_batch_offset` só avança o offset se o merge foi concluído com sucesso.

---

## Alternatives Considered

### Trino como motor do gate

O motor SQL de produção já na stack, sem container adicional.

- **Por que não funciona:** O Trino com `catalog.type=rest` aponta sempre para `main`. Não há
  mecanismo de `session_properties` para selecionar branch com esse tipo de catálogo (validado
  empiricamente: `INVALID_SESSION_PROPERTY` para qualquer tentativa de `iceberg.nessie_reference_name`
  ou equivalente). Rodar `dbt test` via Trino validaria os dados que já estão em `main`, não os
  dados da branch de ingestão — semanticamente incorreto para um gate pré-merge.
- **Rejeitado por:** Incapacidade técnica fundamental, não preferência.

### DuckDB nativo via ATTACH (sem PyIceberg)

Sem container adicional se rodado dentro do Airflow; sem dependência PyIceberg.

- **Por que não funciona:** Dois problemas independentes e não resolvidos:
  1. `ATTACH 'http://nessie:19120/iceberg/main'` retorna 0 tabelas — a extensão `httpfs` do DuckDB
     não implementa a semântica de `prefix` do protocolo Iceberg REST. Branch routing via sufixo de
     URL não é suportado.
  2. Mesmo para `main` (sem branch routing), a leitura dos data files Parquet retorna 403 do MinIO.
     O DuckDB httpfs não propaga o endpoint S3 customizado para URLs resolvidas via catálogo Iceberg
     — ele tenta resolver via AWS SDK padrão, que não tem acesso ao MinIO local.
- **Rejeitado por:** Dois bloqueios técnicos independentes, sem workaround viável.

### Great Expectations como gate de validação

Ferramenta dedicada a data quality com interface visual e histórico de resultados.

- **Pros:** Interface rica, histórico de execuções, integração com Airflow nativa.
- **Cons:** Requer uma stack adicional (Data Docs, backend de resultados). Não resolve o problema
  de conectar à branch Nessie — Great Expectations precisaria do mesmo mecanismo PyIceberg para
  ler os dados da branch. A lógica de validação seria equivalente ao `dbt test`, mas com mais
  infraestrutura e menos legibilidade (Expectations vs. SQL legível por jornalistas).
- **Rejeitado por:** Overhead de stack sem vantagem sobre `dbt test` para o caso de uso. A
  legibilidade do SQL no `sources.yml` é uma vantagem para o público-alvo de jornalistas investigativos
  que precisam auditar a metodologia (ADR 005 — Methodology-as-Code).

### PythonOperator com pyiceberg + pandas

Validações escritas em Python puro dentro do Airflow, sem container adicional.

- **Pros:** Sem build de imagem; direto no PythonOperator.
- **Cons:** Viola ADR 005 (Methodology-as-Code) — validações em Pandas/Python são caixas-pretas
  que não permitem revisão por pares nem geram documentação automática. Viola também ADR 004
  (isolamento entre coleta e análise). O `dbt test` em SQL legível é a metodologia auditável
  exigida pelo contexto jornalístico.
- **Rejeitado por:** Violação direta de ADRs estabelecidos.

---

## Consequences

### Positivos

- **Gate bloqueante e auditável:** `dbt test` com exit code ≠ 0 impede o merge. O log do container
  efêmero registra exatamente quais testes passaram, falharam ou geraram warnings — auditoria
  completa por execução.
- **Branch routing correto:** Cada execução do gate lê exclusivamente os dados da branch de
  ingestão em andamento, não `main`. Isso é semanticamente correto: validamos os dados que serão
  mergeados, não os que já estão em produção.
- **Methodology-as-Code (ADR 005):** As regras de qualidade em `sources.yml` são SQL declarativo,
  versionado no Git, revisável por pares. Um jornalista pode ler e entender cada teste sem
  conhecimento de Python.
- **Isolamento de dependências (ADR 004):** O container `lakehouse-dbt-validator` tem suas próprias
  dependências (`dbt-duckdb`, `pyiceberg`) sem interferir no Airflow ou no Scrapy.
- **Build paralelo:** O overhead de build do validador não adiciona tempo ao caminho crítico —
  ele é construído em paralelo com o `lakehouse-scraper`.

### Negativos

- **Overhead de tempo significativo:** O scan completo de `bronze.lattes_raw` (53.893 linhas,
  Parquet no MinIO) via PyArrow bridge leva ~338 segundos (~5,6 minutos). Isso é o tempo do gate
  sozinho, além do tempo de scraping e carga. Para tabelas maiores, o overhead crescerá
  proporcionalmente. Se o pipeline Lattes escalar para milhões de linhas, o gate precisará ser
  reavaliado (particionamento, seleção de colunas via `scan(selected_fields=[...])`).
- **PyIceberg faz full scan:** O `table.scan().to_arrow()` carrega a tabela inteira para Arrow
  em memória antes de registrá-la no DuckDB. Para um `not_null` simples, isso é desperdício.
  O `dbt-duckdb` não (ainda) suporta pushdown de predicados para o plugin iceberg. Aceitamos
  este trade-off dado o tamanho atual da tabela.
- **Imagem constrói a cada DAG run:** O `build_dbt_validator` reconstrói a imagem `lakehouse-dbt-validator:latest`
  a cada execução do DAG. Docker layer cache mitiga parcialmente isso, mas qualquer mudança
  nas dependências invalida o cache. Uma alternativa futura é pré-construir a imagem durante
  o deploy da plataforma e remover o build do DAG — mas isso exigiria um processo de release
  para a imagem, que aumenta a complexidade operacional.
- **Dependência de versões pip não pinadas:** `dbt-core` e `DuckDB` são resolvidos pelo `pip`
  em tempo de build. Uma atualização upstream pode quebrar a compatibilidade silenciosamente.
  Monitorar releases de `dbt-duckdb` e `pyiceberg` para ajuste proativo.
- **Acoplamento ao alias do plugin:** O `sources.yml` referencia `plugin: iceberg_branch` e o
  `profiles.yml` declara `alias: iceberg_branch`. Renomear o alias em um sem atualizar o outro
  quebra o gate silenciosamente (dbt não valida referências de plugin em tempo de parse).

---

## Notes

**Estado de implementação (maio de 2026):**

- ✅ Issue #59: piloto do branching no pipeline `lattes_ssd` — ativado via YAML
- ✅ Issue #60: gate `dbt_test_branch` integrado ao `factory.py`
- ✅ Validado empiricamente: PASS=3, WARN=1, ERROR=0 em 53.893 linhas (338s)
- ✅ `dbt/branch_validator/` commitado na branch `dbt`, PR para `main` aberto

**Próximos passos recomendados:**

- Avaliar `scan(selected_fields=[...])` no plugin iceberg para reduzir o volume de dados
  transferidos para Arrow (otimização de performance do gate).
- Adicionar testes de schema evolution no `sources.yml` conforme novos campos são adicionados
  ao spider Lattes.
- Estender o padrão para as demais fontes ativas (`caruaru`, CNPJ) à medida que seus pipelines
  forem promovidos para `branching: enabled: true`.
- Avaliar cache de imagem Docker para `lakehouse-dbt-validator` no processo de deploy, eliminando
  o `build_dbt_validator` do grafo do DAG.

**Referências técnicas:**

- Código-fonte do plugin iceberg do dbt-duckdb: `dbt/adapters/duckdb/plugins/iceberg.py`
- PyIceberg RestCatalog com prefix routing: `pyiceberg.catalog.rest.RestCatalog`
- Protocolo Iceberg REST spec: https://iceberg.apache.org/rest-api-spec/ (campo `prefix` em
  `namespace` e `table` endpoints)
- Nessie REST API v2: https://projectnessie.org/nessie-latest/rest-api-spec/
