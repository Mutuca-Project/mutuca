# Padrões de Desenvolvimento

Convenções e padrões estabelecidos no projeto. Seguir esses padrões garante consistência entre pipelines, facilita revisão de código e mantém a rastreabilidade metodológica exigida pelo jornalismo de dados.

---

## Arquitetura de spiders

### Padrão spider/collector

Todo spider que envolve transformação de dados não-trivial deve separar responsabilidades em duas camadas:

**Spider** — orquestra o fluxo HTTP:

- Dispara e pagina requisições
- Valida integridade dos dados recebidos (ex: código numérico válido)
- Delega mapeamento e construção de itens ao collector

**Collector** (em `mutuca/core/`) — transforma dados:

- Métodos puros (stateless): `dict` entra, `dict`/`Item` sai
- Sem efeitos colaterais (sem HTTP, sem IO)
- Testável de forma completamente isolada, sem Scrapy

```python
# Spider — apenas orquestração
class MeuSpider(scrapy.Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collector = MeuCollector()

    def parse_pagina(self, response):
        dados = self.collector.extrair_dados(response.json())
        yield scrapy.Request(url=..., cb_kwargs={"dados": dados})

    def parse_detalhe(self, response, dados):
        yield self.collector.construir_item(dados, response.json())
```

```python
# Collector — apenas transformação
class MeuCollector:
    def extrair_dados(self, payload: dict) -> dict:
        return {"campo": payload.get("campoAPI", "")}

    def construir_item(self, dados: dict, detalhe: dict) -> MeuItem:
        return MeuItem(campo=dados["campo"], ...)
```

Este padrão é implementado em `CaruaruPublicWorksDataCollector` (Caruaru) e `CguEmendasCollector` (CGU).

---

### `scrapy.Item` em vez de `dict`

Sempre use `scrapy.Item` com campos declarados explicitamente em `mutuca/items/`. Nunca faça `yield {}` diretamente no spider.

```python
# ✅ Correto
class EmendaParlamentarItem(scrapy.Item):
    codigo_emenda = scrapy.Field()
    favorecido    = scrapy.Field()
    # ...

yield EmendaParlamentarItem(codigo_emenda="...", favorecido="...")

# ❌ Incorreto — sem contrato de schema, sem validação
yield {"codigo_emenda": "...", "favorecido": "..."}
```

Vantagens do `scrapy.Item`: o Scrapy levanta `KeyError` em campos desconhecidos (guarda de schema durante desenvolvimento) e o schema serve como documentação viva.

---

### `data_extracao` — responsabilidade do loader

O campo `data_extracao` **não deve estar nos itens do spider**. É adicionado pelo `iceberg_loader` como `TIMESTAMP WITH TIME ZONE` no momento da carga, garantindo consistência de tipo e valor em todos os pipelines.

---

## Tratamento de erros

Use `utils/error_handlers.py` para errbacks em `scrapy.Request`. Nunca implemente `handle_error` como método do spider.

```python
from mutuca.utils.error_handlers import handle_request_error

yield scrapy.Request(
    url=url,
    callback=self.parse,
    errback=lambda f: handle_request_error(f, self.log),
)
```

`handle_request_error` distingue `HttpError`, `DNSLookupError`, `TimeoutError` e erros genéricos, logando com campos JSON estruturados compatíveis com o formatter do Airflow.

---

## Logger estruturado

Use `get_logger` de `utils/logger.py` em vez de `self.logger` (padrão Scrapy). A saída é em JSON, compatível com o parsing de logs do Airflow.

```python
from mutuca.utils.logger import get_logger

class MeuSpider(scrapy.Spider):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.log = get_logger(self.name)

    def parse(self, response):
        self.log.info("Processando", extra={"url": response.url, "status": response.status})
```

---

## Testes

### Duas camadas de testes para cada pipeline

**Testes unitários do collector** (`tests/core/test_<fonte>_collector.py`):

- Testam os métodos do collector de forma completamente isolada
- Sem Scrapy, sem fixtures JSON, sem HTTP
- Entrada e saída são `dict` e `Item` puros
- Rápidos e determinísticos

**Testes de integração/fumaça do spider** (`tests/spiders/<fonte>/test_<spider>.py`):

- Testam o comportamento dos callbacks com respostas HTTP falsas
- Usam `scrapy.http.TextResponse` construída a partir de fixtures JSON
- Verificam orquestração: paginação, dispatch de requests, tipos de saída

### Por que não é antipadrão testar spiders

Os testes não verificam se a API de terceiros retorna o esperado — isso seria antipadrão. Verificam a **lógica do nosso código** dado uma entrada fixa. As fixtures JSON são contratos explícitos: quando a API mudar seu formato, o ciclo é: inspecionar → corrigir spider → atualizar fixture → rodar testes → commit atômico.

### `conftest.py` e a factory `fake_response`

```python
# tests/conftest.py
def fake_response(fixture_path, url="...", meta=None, cb_kwargs=None):
    """Cria TextResponse a partir de fixture JSON — zero HTTP."""
    body = (FIXTURES_DIR / fixture_path).read_bytes()
    request = scrapy.http.Request(url=url, meta=meta or {}, cb_kwargs=cb_kwargs or {})
    return scrapy.http.TextResponse(url=url, body=body, encoding="utf-8", request=request)
```

### Execução

```bash
cd scrapy/
source .venv/bin/activate
pytest tests/ -v                          # suite completa
pytest tests/core/ -v                     # apenas unitários
pytest tests/spiders/ -v                  # apenas integração
```

---

## Convenções de commit

Todos os commits seguem o padrão [Conventional Commits](https://www.conventionalcommits.org/) **em português do Brasil**.

### Formato

```
tipo(escopo): descrição curta em português

Corpo explicativo com contexto, decisões de design e impacto.
Use seções com linhas separadoras (───) para múltiplos tópicos.
```

### Tipos utilizados

| Tipo | Quando usar |
|---|---|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `refactor` | Refatoração sem mudança de comportamento |
| `test` | Adição ou modificação de testes |
| `docs` | Documentação |
| `chore` | Tarefas de manutenção (deps, config) |

### Escopos comuns

`scrapy/cgu`, `scrapy/<fonte>`, `airflow`, `dbt`, `dados`, `infra`, `docs`

### Exemplo

```
fix(scrapy/cgu): corrige dois bugs críticos de qualidade de dados no A2

─────────────────────────────────────────────────────────────────────
Bug 1 — Emendas com codigoEmenda inválido contaminam a base
─────────────────────────────────────────────────────────────────────
Causa: a API da CGU retorna valores não-numéricos ('S/I', 'REL. GERAL')
...

─────────────────────────────────────────────────────────────────────
Bug 2 — Truncamento silencioso de emendas com mais de 1.000 documentos
─────────────────────────────────────────────────────────────────────
...
```

Commits com múltiplas mudanças relacionadas devem usar seções separadoras para documentar cada alteração individualmente.
