# Padrões de desenvolvimento

Convenções estabelecidas no projeto para garantir consistência entre pipelines, facilitar revisão de código e manter a rastreabilidade metodológica que o jornalismo de dados exige.

---

## Por que padronizar?

Em um projeto de jornalismo investigativo, o código não é apenas ferramenta — é parte da metodologia. Quando uma reportagem cita dados coletados automaticamente, os leitores precisam poder entender e reproduzir a coleta. Padrões inconsistentes tornam isso difícil.

Além disso, o projeto tem um único servidor com recursos limitados e é mantido por uma equipe pequena. Padrões simples e claros reduzem o tempo de onboarding e o risco de introduzir bugs silenciosos.

---

## Arquitetura de spiders: separação entre orquestração e transformação

Todo spider que envolve processamento de dados além de uma extração simples separa responsabilidades em duas camadas.

**O spider** cuida exclusivamente do fluxo HTTP: dispara requisições, pagina endpoints, valida integridade básica (como checar se um código é numérico válido antes de fazer outra chamada) e repassa os dados para o collector.

**O collector** (em `mutuca/core/`) cuida exclusivamente da transformação: mapeia campos da API para o esquema interno, monta parâmetros de consulta, constrói os itens de saída. Os métodos do collector são funções puras — recebem dicionários e devolvem dicionários ou itens, sem efeitos colaterais, sem chamadas HTTP, sem IO.

Essa separação tem uma consequência direta para os testes: é possível testar toda a lógica de transformação de dados sem precisar simular um servidor HTTP. Isso torna os testes mais rápidos, mais determinísticos e mais fáceis de manter.

O padrão está implementado em `CguEmendasCollector` (pipeline CGU) e `CaruaruPublicWorksDataCollector` (pipeline Caruaru).

---

## Itens Scrapy com campos declarados

A saída de cada spider é um `scrapy.Item` com todos os campos declarados explicitamente em `mutuca/items/`. Nunca se usa um dicionário simples no `yield` do spider.

A vantagem prática: o Scrapy levanta um erro imediatamente se o código tentar popular um campo que não existe no item. Isso funciona como uma guarda de schema durante o desenvolvimento — o erro aparece na hora errada do spider, não depois quando o dado já está no banco.

Como consequência, o arquivo de item serve como documentação viva do schema de saída do spider. Qualquer pessoa que queira entender o que o pipeline coleta pode olhar para o arquivo de item e ter uma resposta clara.

---

## `data_extracao` é responsabilidade do pipeline, não do spider

O campo `data_extracao` — que registra quando o dado foi carregado no Lakehouse — não deve aparecer nos itens do spider. Ele é adicionado pelo `iceberg_loader` no momento da carga, como `TIMESTAMP WITH TIME ZONE`, de forma uniforme em todos os pipelines.

Essa decisão garante consistência de tipo e valor entre todas as tabelas Bronze: a coluna sempre tem o mesmo tipo e sempre representa o momento exato da carga, independente de como cada spider foi implementado.

---

## Tratamento de erros em requisições

O módulo `utils/error_handlers.py` fornece a função `handle_request_error`, usada como errback em todas as requisições. Ela distingue entre erros HTTP (com código de status), erros de DNS, timeouts e outros erros do protocolo, logando cada caso com campos estruturados compatíveis com o formato de log do Airflow.

Nenhum spider implementa seu próprio método `handle_error` — todos delegam para esse utilitário via lambda.

---

## Logger estruturado

Todos os spiders usam `get_logger` de `utils/logger.py` em vez do `self.logger` padrão do Scrapy. A diferença é o formato de saída: o logger do projeto produz JSON, que o Airflow consegue parsear e indexar corretamente nos logs de execução do DAG.

---

## Testes

### Por que testar spiders não é antipadrão

Existe uma crítica legítima a testes de spider: se o teste verifica que a API de terceiros retorna o dado esperado, ele vai falhar toda vez que a API mudar — e você não controla isso.

Os testes do projeto não fazem isso. Eles verificam a **lógica interna do código** dado uma entrada fixa. A fixture JSON é um contrato explícito: "assumindo que a API responde com esse formato, o spider deve se comportar assim". Quando a API mudar o formato, o ciclo é direto — inspecionar a mudança, corrigir o spider, atualizar a fixture, rodar os testes, fazer o commit. O commit atômico documenta exatamente quando e como a fonte mudou, o que tem valor para a cadeia de custódia da investigação.

### Duas camadas

**Testes unitários do collector** (`tests/core/`): testam os métodos de transformação de dados de forma completamente isolada. Não usam Scrapy, não leem arquivos, não fazem HTTP. Apenas `dict` entra e `dict` ou `Item` sai. São rápidos e podem ser rodados a qualquer momento sem nenhuma dependência externa.

**Testes de integração do spider** (`tests/spiders/`): testam o comportamento dos callbacks com respostas HTTP simuladas. Usam `scrapy.http.TextResponse` construída a partir de arquivos de fixture JSON. Verificam paginação, dispatch de requests, tipos de saída e tratamento de payloads inválidos.

---

## Convenções de commit

Todos os commits seguem o padrão [Conventional Commits](https://www.conventionalcommits.org/) em **português do Brasil**.

O formato é `tipo(escopo): descrição curta`, seguido de um corpo explicativo quando necessário. Para commits que corrigem bugs ou introduzem decisões de design relevantes, o corpo documenta a causa, o impacto e a solução — esse texto permanece no histórico do repositório e serve como registro metodológico da investigação.

| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `refactor` | Reestruturação sem mudança de comportamento |
| `test` | Adição ou modificação de testes |
| `docs` | Documentação |
| `chore` | Manutenção (dependências, configuração) |

Escopos comuns: `scrapy/cgu`, `scrapy/<fonte>`, `airflow`, `dbt`, `dados`, `infra`, `docs`.
