## Context

A criação de novos pipelines de ingestão no Mutuca exigia que o responsável pelo pipeline
escrevesse código Python para definir o DAG no Airflow. Esse requisito criava duas tensões
diretas com os princípios do projeto:

1. **Barreira de entrada:** Jornalistas investigativos e pesquisadores — o público-alvo do
   Mutuca — não são necessariamente programadores. Exigir conhecimento de Python e da API do
   Airflow para adicionar uma nova fonte de dados contradiz o objetivo de democratização da
   ferramenta.

2. **Duplicação estrutural:** Todos os pipelines de ingestão seguem o mesmo fluxo:
   `setup_docker_env → DockerOperator(scrapy) → [load_to_iceberg] → [offset_control]`. Com um
   arquivo Python por pipeline, a estrutura era repetida integralmente em cada DAG, tornando
   manutenções (ex: mudança na rede Docker, renomeação de imagem) um trabalho de busca-e-troca
   em múltiplos arquivos.

O problema não era a complexidade de cada pipeline individualmente, mas a ausência de uma
separação clara entre **o que o pipeline faz** (configuração) e **como o pipeline funciona**
(estrutura).

## Decision

Adotei o padrão **YAML-Driven DAG Factory**: a estrutura de todos os DAGs de ingestão é
gerada dinamicamente por um único módulo Python (`factory.py`), enquanto a configuração
específica de cada pipeline é declarada em um arquivo YAML independente.

A arquitetura resultante tem três camadas:

```
airflow/dags/
├── factory.py            ← estrutura: lê os YAMLs e gera DAGs via API do Airflow
├── pipelines/
│   ├── caruaru.yaml      ← configuração: o QUE este pipeline faz
│   └── lattes.yaml
└── shared/
    └── iceberg_loader.py ← comportamento reutilizável: carga genérica no Iceberg
```

**O que vai no YAML (configuração — acessível a não-programadores):**

- Identificação do DAG (`dag_id`, `description`, `owner`, `schedule`)
- Spider a executar e seus parâmetros (`scrapy.spider`, `scrapy.settings`)
- Volumes montados para fontes de dados locais (`scrapy.mounts`)
- Destino da carga Iceberg (`load_iceberg.source_glob`, `target_schema`, `target_table`)
- Renomeação opcional de campos do JSONL para colunas da tabela (`load_iceberg.rename`)
- Controle de offset para ingestão em lotes (`offset_control.variable`, `batch_size`)

**O que vai no `factory.py` (estrutura — mantido por engenheiros):**

- Construção do comando `scrapy crawl` com parâmetros dinâmicos
- Criação de `BashOperator`, `DockerOperator` e `PythonOperator` via API do Airflow
- Injeção de credenciais MinIO via `BaseHook`
- Montagem da cadeia de dependências entre tasks

**O que vai no `iceberg_loader.py` (comportamento genérico):**

- Leitura de JSONL do MinIO via glob
- Detecção automática de colunas a partir do DataFrame (sem declaração de schema no YAML)
- Serialização automática de tipos complexos (`dict`/`list` → `json.dumps`)
- Inserção em batch no Trino com `CURRENT_TIMESTAMP` como `data_extracao`
- Movimentação de arquivos processados para `processed/`

Para adicionar um novo pipeline, basta criar `pipelines/<nova_fonte>.yaml`. Nenhum Python
novo é necessário para o caso padrão.

## Alternatives Considered

**Um arquivo Python por pipeline (padrão anterior):**

- **Pros:** Familiaridade; depuração direta no Airflow.
- **Cons:** Duplicação da estrutura do DAG em cada arquivo; exige Python para qualquer
  alteração de configuração (schedule, spider, mounts).
- **Rejeitado por:** Violação do princípio de acessibilidade e alto custo de manutenção.

**Biblioteca `dag-factory` (PyPI):**

- **Pros:** Solução pronta; bem documentada.
- **Cons:** Projetada para o caso genérico do Airflow — não conhece os padrões específicos do
  Mutuca (DooD, `lakehouse-net`, `minio_s3_connection`, offset control). O YAML resultante
  seria mais verboso que a solução customizada, expondo detalhes internos do Airflow ao
  usuário.
- **Rejeitado por:** Abstração inadequada para o contexto; dependência externa desnecessária.

**Schema de colunas declarado no YAML:**

Variante considerada durante o design do `iceberg_loader`: declarar explicitamente cada
coluna e seu tipo no YAML (ex: `{field: nome, type: string}`).

- **Pros:** Schema auditável no controle de versão.
- **Cons:** Verboso; redundante com a definição de tabela que já existe no Trino; exigiria
  atualização do YAML a cada mudança de campo no scraper.
- **Rejeitado por:** A detecção automática de colunas a partir do DataFrame é suficiente para
  a camada Bronze, onde o dado bruto deve ser preservado integralmente. O schema canônico
  é e deve ser a definição da tabela no Trino.

## Consequences

**Positivos:**

- **Acessibilidade:** Um novo pipeline pode ser criado preenchendo um formulário YAML sem
  escrever código Python. O YAML serve como documentação da fonte: o que coleta, onde deposita,
  qual schedule.
- **Manutenibilidade:** Mudanças estruturais (ex: renomear a imagem Docker, mudar a rede,
  alterar padrão de log) são feitas em um único lugar — `factory.py` — e propagadas
  automaticamente para todos os pipelines.
- **Genericidade do loader:** `iceberg_loader.py` carrega qualquer JSONL em qualquer tabela
  Bronze sem modificação. O mesmo módulo serve para Lattes, Caruaru e qualquer fonte futura.
- **Rastreabilidade:** O histórico de mudanças de um pipeline (schedule, spider, mounts) fica
  no git como diff de YAML, legível por qualquer colaborador.

**Negativos:**

- **Concentração de complexidade:** `factory.py` é o ponto de falha único para todos os DAGs.
  Um erro de sintaxe nele derruba o parsing de todos os pipelines no Airflow.
- **Limite do caso padrão:** Pipelines que precisam de tasks fora do fluxo padrão
  (`setup → scrapy → load → offset`) ainda exigirão Python. O YAML não substitui a
  expressividade da API do Airflow para casos excepcionais.
- **Pré-requisito de tabela:** O `iceberg_loader` não cria tabelas — elas devem existir no
  Trino previamente. A criação de tabela é responsabilidade de infraestrutura, fora do
  pipeline.

## Notes

Este padrão é intencionalmente conservador: resolve o caso padrão (>90% dos pipelines
esperados) com YAML simples, sem tentar ser um framework completo. Casos excepcionais
continuam sendo resolvidos em Python diretamente — a factory não precisa cobrir tudo.

O `.airflowignore` em `dags/` exclui `shared/` e `pipelines/` do scanner de DAGs do
Airflow, evitando falsos positivos de importação.
