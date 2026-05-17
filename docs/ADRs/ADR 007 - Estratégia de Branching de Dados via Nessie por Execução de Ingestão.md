## Context

O Mutuca coleta dados de portais governamentais que podem alterar ou apagar informações após a
publicação de uma reportagem. A camada Bronze já preserva o arquivo original no MinIO (ADR 004), mas
o catálogo Iceberg no Trino não oferece, por si só, isolamento entre uma ingestão em andamento e os
dados já validados. Sem isolamento, um lote com dados malformados, duplicados ou com schema
inesperado é inserido diretamente na tabela de produção — e só é detectado depois, quando já
contaminou as análises.

Há também uma exigência jornalística que vai além da engenharia: cada execução de pipeline deve ser
rastreável como uma unidade atômica e auditável. Saber **exatamente quais dados foram adicionados em
qual execução**, com possibilidade de desfazer uma ingestão específica sem afetar as demais, é o
equivalente de dados ao "histórico de edições" de um documento jornalístico.

O Nessie — já presente na stack como catálogo Iceberg com versionamento Git-like — oferece
precisamente esse mecanismo via branches de dados.

## Decision

Adotei o padrão **branching por execução de ingestão via Nessie**: cada execução de DAG que inclui
carga Iceberg abre uma branch isolada, carrega os dados nela, valida com `dbt test`, e só então
faz merge para `main`. Se a validação falhar, a branch é deletada sem deixar rastro na camada de
produção.

O fluxo padrão gerado pelo `factory.py` para pipelines com `branching: enabled: true` no YAML é:

```
create_nessie_branch
        │
setup_docker_env
        │
scrapy (DockerOperator)          ← sem alterações
        │
load_iceberg                     ← recebe nome da branch via XCom
        │
dbt_test (na branch)             ← valida dados antes do merge
        │
   (falhou)    (passou)
delete_branch  merge_to_main
               increment_offset
               delete_branch
```

**Convenção de nomes de branch:** `ingest_{dag_id}_{YYYYMMDD_HHmmss}`

Exemplos: `ingest_lattes_ssd_20260516_143022`, `ingest_caruaru_cityhall_20260601_090000`

O nome único por execução garante que duas execuções simultâneas (improvável dado `max_active_runs=1`,
mas possível em diferentes DAGs) nunca colidam.

**Ambiente técnico validado na Fase 1 (maio de 2026):**

- Nessie versão 0.95.0, spec 2.1.0, API v2
- Backend: JDBC/PostgreSQL (tabelas inicializadas automaticamente na primeira subida)
- Endpoint correto para listar branches: `GET /api/v2/trees`
- Criação de branches via `pynessie >= 0.67` usando base URL `/api/v1` (a biblioteca negocia
  a versão da API automaticamente via `/api/v2/config`)
- Validado empiricamente: branch `main` existe com hash estável; todas as 4 operações de lifecycle
  (create / hash / merge / delete) validadas com sucesso via `airflow/dags/shared/nessie_client.py`
- `pynessie` instalado no container Airflow via `airflow/requirements.txt` (pip com constraint
  do Airflow 2.10.4). Venv separado em `infrastructure/nessie/.venv` mantido apenas para
  diagnóstico de infraestrutura no host.
- Mecanismo de escrita em branch validado (issue #56): `RestCatalog` do PyIceberg com
  `prefix=branch_name` é a única abordagem funcional. `iceberg.nessie_reference_name` via
  `session_properties` do Trino não existe com `catalog.type=rest` (retorna
  `INVALID_SESSION_PROPERTY`). Namespace aninhado `iceberg."BRANCH.schema".table` retorna
  `NOT_SUPPORTED`.

A seção `branching` no YAML do pipeline é **opt-in**: pipelines que não declaram essa seção
continuam com o fluxo atual sem modificação. Isso permite migrar cada fonte progressivamente,
começando por `lattes_ssd` como piloto (issue #59).

## Alternatives Considered

**Escrita direta em `main` com rollback manual:**

- **Pros:** Simplicidade; sem dependência do Nessie para o fluxo de ingestão.
- **Cons:** Um lote corrompido contamina a camada de produção imediatamente. Rollback exige
  identificar e deletar manualmente os arquivos Parquet no MinIO e as entradas no catálogo Iceberg
  — processo propenso a erro e sem garantia de completude.
- **Rejeitado por:** Ausência de isolamento. Incompatível com o princípio de auditabilidade
  jornalística: não há como provar que "estes dados e somente estes dados" foram adicionados por
  uma execução específica.

**LakeFS como camada de versionamento:**

- **Pros:** Interface Git completa, incluindo diff de dados e integração com S3.
- **Cons:** Não integrado ao stack atual. Exigiria substituir o Nessie — que já está rodando e
  integrado ao Trino via catálogo Iceberg — por um serviço adicional com footprint de memória
  próprio, em hardware de 16GB já no limite.
- **Rejeitado por:** Nessie já entrega o versionamento necessário sem custo adicional de memória
  ou refatoração do Trino.

**Branches por ambiente (dev/prod), não por execução:**

- **Pros:** Familiar para quem vem de Git de código; `main` seria sempre "produção".
- **Cons:** Não resolve o problema de isolamento por ingestão — um dado ruim carregado em `dev`
  ainda contaminaria `dev`, e o merge para `main` seria um passo manual sem automação. Cria
  também complexidade de configuração no Trino (`session_properties` por branch) para dois
  ambientes permanentes.
- **Rejeitado por:** Complexidade sem benefício real. O isolamento necessário é temporal
  (por execução), não ambiental.

**Branch por fonte de dados (permanente), não por execução:**

- **Pros:** Menos branches; merge menos frequente.
- **Cons:** Uma branch `lattes` permanente acumula todas as ingestões sem isolamento entre elas.
  O objetivo é isolar cada *execução* para permitir rollback granular — um esquema de branch
  permanente por fonte não oferece isso.
- **Rejeitado por:** Não atende ao requisito de auditabilidade por execução.

## Consequences

**Positivos:**

- **Rollback atômico:** Se `dbt test` falhar, a branch é deletada sem afetar `main`. Nenhum dado
  ruim chega à camada de produção. O dado bruto original continua preservado no MinIO (ADR 004).
- **Rastreabilidade por execução:** O histórico de commits do Nessie em `main` mostra exatamente
  quais lotes foram aceitos e quando, servindo como log de auditoria da investigação.
- **Validação antes da publicação:** O gate `dbt test` garante que regras de qualidade (nulos,
  duplicatas, CPFs inválidos) são verificadas antes de qualquer dado chegar às camadas Silver/Gold.
- **`main` sempre estável:** Analistas e jornalistas que consultam o Trino apontando para `main`
  nunca veem dados em estado parcial ou em processo de validação.
- **Migração incremental:** O `opt-in` via YAML permite ativar o branching fonte por fonte, sem
  refatoração global dos pipelines existentes.

**Negativos:**

- **Dependência do pynessie:** A biblioteca `pynessie` tem histórico de mudanças de API entre
  versões maiores. Atualizações do servidor Nessie podem requerer atualização coordenada do
  cliente Python.
- **Responsabilidade de limpeza de branches:** Branches de execuções antigas (sejam bem-sucedidas
  ou falhas) não são deletadas automaticamente pelo Nessie. O `factory.py` deve garantir a deleção
  em ambos os caminhos (sucesso e falha). Branches órfãs acumuladas degradam a performance das
  listagens do catálogo.
- **Escrita em branch via PyIceberg, não via Trino:** O `load_iceberg` e o `dbt_test` precisam
  usar o `RestCatalog` do PyIceberg com `prefix=branch_name` para escrever e ler na branch correta.
  O Trino não suporta seleção de branch via `session_properties` com `catalog.type=rest` — tentativas
  retornam `INVALID_SESSION_PROPERTY`. Isso implica uma arquitetura split: PyIceberg para escrita em
  branches de ingestão; Trino para consultas analíticas (sempre aponta para `main`). A integração
  do `iceberg_loader.py` com PyIceberg é realizada na issue #55.
- **Nessie/PostgreSQL como ponto único de falha:** Se o catálogo Nessie estiver indisponível,
  nenhuma ingestão com branching pode prosseguir. O design atual não prevê fallback para escrita
  direta em `main` — isso é intencional (não contaminar produção), mas implica que a disponibilidade
  do Nessie é requisito de produção.

## Notes

**Estado de implementação (maio de 2026):**

- ✅ Issues #53, #54: ambiente Nessie operacional e pynessie funcionando
- ✅ Issue #56: mecanismo de escrita em branch definido (PyIceberg `RestCatalog` com `prefix`)
- ✅ Issue #55: `airflow/dags/shared/nessie_client.py` implementado e validado (create / merge / delete)
- 🔧 Issue #57: seção `branching` no YAML dos pipelines (próximo passo)
- 🔧 Issue #58: atualização do `factory.py` para gerar as tasks de branching
- 🔜 Issue #59: piloto no pipeline `lattes_ssd`
- 🔜 Issue #60: integração do `dbt test` como gate de validação

O caminho crítico atual é #57 → #58 → #59. O piloto `lattes_ssd` será o primeiro pipeline a
ativar o branching em produção. A extensão aos demais pipelines ocorre após o piloto validado.
