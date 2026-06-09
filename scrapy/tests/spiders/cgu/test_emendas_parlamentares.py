"""
Testes de integração (fumaça) — EmendasParlamentaresSpider

Valida o comportamento dos callbacks sem realizar chamadas HTTP reais.
Cada teste isola um aspecto específico do spider usando fixtures JSON
que reproduzem fielmente o formato da API da CGU.

Classes de teste:
  TestStartRequests                  — URL, parâmetros de= ate= e meta offset inicial
  TestParseEmendas                   — paginação A1, dispatch de requests A2
  TestParseEmendasComCodigoInvalido  — filtro de emendas S/I e REL. GERAL antes do A2
  TestParseDocumentos                — yield de items, campos A1/A2, JSON inválido, A2 vazio
  TestParseDocumentosPaginacao       — paginação do A2 quando recordsTotal > PAGE_SIZE_A2

Contexto de TestParseEmendasComCodigoInvalido:
  Emendas com codigoEmenda='S/I' ou 'REL. GERAL' fazem a API do A2 retornar
  resultados inflados (até 403.000 docs) por ignorar o filtro de código.
  O spider deve detectar esses casos via collector.codigo_emenda_valido() e
  pular o dispatch do request A2.

Contexto de TestParseDocumentosPaginacao:
  Emendas de Relator (sk_tipo_emenda=5) podem ter >1000 documentos. O spider
  deve paginar o A2 da mesma forma que o A1: enquanto offset + PAGE_SIZE < recordsTotal,
  despacha nova requisição com offset incrementado.

Execução:
    cd scrapy/
    pytest tests/spiders/cgu/test_emendas_parlamentares.py -v
"""

import scrapy
from mutuca.items.cgu_emendas_item import EmendaParlamentarItem
from mutuca.spiders.cgu.emendas_parlamentares import (
    BASE_A1,
    BASE_A2,
    EmendasParlamentaresSpider,
)
from tests.conftest import fake_response

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect(generator) -> list:
    """Drena um generator e retorna uma lista com todos os objetos."""
    return list(generator)


def _requests(items: list) -> list[scrapy.Request]:
    return [i for i in items if isinstance(i, scrapy.Request)]


def _emenda_items(items: list) -> list[EmendaParlamentarItem]:
    return [i for i in items if isinstance(i, EmendaParlamentarItem)]


# ---------------------------------------------------------------------------
# Grupo 1 — start_requests
# ---------------------------------------------------------------------------


class TestStartRequests:

    def test_url_contem_base_a1(self, spider_cgu):
        """A primeira requisição deve apontar para o endpoint A1 da CGU."""
        requests = _collect(spider_cgu.start_requests())
        assert len(requests) == 1
        assert BASE_A1 in requests[0].url

    def test_url_contem_parametros_de_ate(self, spider_cgu):
        """Os parâmetros de= e ate= devem estar presentes na URL inicial."""
        requests = _collect(spider_cgu.start_requests())
        url = requests[0].url
        assert "de=2026" in url
        assert "ate=2026" in url

    def test_meta_offset_inicial_e_zero(self, spider_cgu):
        """O meta offset da primeira requisição deve ser 0."""
        requests = _collect(spider_cgu.start_requests())
        assert requests[0].meta["offset"] == 0


# ---------------------------------------------------------------------------
# Grupo 2 — parse_emendas (callback A1)
# ---------------------------------------------------------------------------


class TestParseEmendas:

    def test_retorna_um_request_a2_por_emenda(self, spider_cgu):
        """2 emendas no A1 → 2 requests para o endpoint A2."""
        response = fake_response("cgu/a1_response.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a2_requests = [r for r in _requests(results) if BASE_A2 in r.url]
        assert len(a2_requests) == 2

    def test_pagina_quando_ha_mais_registros(self, spider_cgu):
        """
        total=2000, página com 1 item → deve gerar 1 request A2 + 1 request de paginação A1.
        """
        response = fake_response("cgu/a1_paginated.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        all_requests = _requests(results)
        a1_requests = [r for r in all_requests if BASE_A1 in r.url]
        a2_requests = [r for r in all_requests if BASE_A2 in r.url]
        assert len(a2_requests) == 1, "Deve ter 1 request A2 para a emenda da página"
        assert (
            len(a1_requests) == 1
        ), "Deve ter 1 request de paginação para o próximo offset"

    def test_proximo_offset_e_incrementado_corretamente(self, spider_cgu):
        """O offset do request de paginação deve ser PAGE_SIZE_A1 (1000)."""
        response = fake_response("cgu/a1_paginated.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a1_next = next(r for r in _requests(results) if BASE_A1 in r.url)
        assert "offset=1000" in a1_next.url

    def test_nao_pagina_quando_registros_esgotados(self, spider_cgu):
        """
        total=2, página com 2 itens → apenas 2 requests A2, nenhum request A1 adicional.
        """
        response = fake_response("cgu/a1_response.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a1_requests = [r for r in _requests(results) if BASE_A1 in r.url]
        assert len(a1_requests) == 0

    def test_json_invalido_nao_causa_excecao(self, spider_cgu):
        """Payload corrompido deve logar erro e retornar sem levantar exceção."""
        import scrapy.http

        bad_request = scrapy.http.Request(
            url="https://portaldatransparencia.gov.br/fake",
            meta={"offset": 0},
        )
        bad_response = scrapy.http.TextResponse(
            url="https://portaldatransparencia.gov.br/fake",
            body=b"isso nao e json {{{",
            encoding="utf-8",
            request=bad_request,
        )

        # Não deve levantar exceção
        results = _collect(spider_cgu.parse_emendas(bad_response))
        assert results == []


# ---------------------------------------------------------------------------
# Grupo 3 — parse_documentos (callback A2)
# ---------------------------------------------------------------------------

_DADOS_A1_EXEMPLO = {
    "autor": "3900 - ADRIANO DO BALDY",
    "codigo_emenda": "202639000008",
    "tipo_emenda": "Emenda Individual - Transferências com Finalidade Definida",
    "sk_tipo_emenda": 2,
    "localidade_do_gasto": "MÚLTIPLO",
    "codigo_funcao": "10",
    "funcao": "Saúde",
    "codigo_subfuncao": "302",
    "subfuncao": "Assistência hospitalar e ambulatorial",
    "programa": "5118 - ATENCAO ESPECIALIZADA A SAUDE",
    "acao": "2E90 - INCREMENTO TEMPORARIO AO CUSTEIO DOS SERVICOS",
    "plano_orcamentario": "INCREMENTO TEMPORARIO AO CUSTEIO DOS SERVICOS",
    "numero_emenda": "0008",
    "ano": 2026,
    "valor_total_a1": "1.653.375,00",
    "valor_empenhado": "3.053.375,00",
    "valor_liquidado": "1.653.375,00",
    "valor_resto_inscrito": "0,00",
    "valor_resto_cancelado": "0,00",
    "valor_resto_pago": "0,00",
    "possui_apoio_solicitante": "Não se aplica",
}


class TestParseDocumentos:

    def test_retorna_emenda_parlamentar_item(self, spider_cgu):
        """O yield deve ser instâncias de EmendaParlamentarItem, não dicts."""
        response = fake_response(
            "cgu/a2_response.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        items = _emenda_items(
            _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO))
        )
        assert len(items) == 2
        assert all(isinstance(i, EmendaParlamentarItem) for i in items)

    def test_item_tem_data_extracao_preenchida(self, spider_cgu):
        """data_extracao deve estar presente e não vazio em todos os items."""
        response = fake_response(
            "cgu/a2_response.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        items = _emenda_items(
            _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO))
        )
        for item in items:
            assert "data_extracao" in item
            assert item["data_extracao"]  # não vazio

    def test_campos_a1_sao_propagados_corretamente(self, spider_cgu):
        """Todos os campos do A1 (dados_a1) devem aparecer intactos no Item."""
        response = fake_response(
            "cgu/a2_response.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        items = _emenda_items(
            _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO))
        )
        item = items[0]

        assert item["autor"] == _DADOS_A1_EXEMPLO["autor"]
        assert item["codigo_emenda"] == _DADOS_A1_EXEMPLO["codigo_emenda"]
        assert item["tipo_emenda"] == _DADOS_A1_EXEMPLO["tipo_emenda"]
        assert item["numero_emenda"] == _DADOS_A1_EXEMPLO["numero_emenda"]
        assert item["ano"] == _DADOS_A1_EXEMPLO["ano"]
        assert item["funcao"] == _DADOS_A1_EXEMPLO["funcao"]
        assert item["valor_empenhado"] == _DADOS_A1_EXEMPLO["valor_empenhado"]

    def test_campos_a2_sao_extraidos_corretamente(self, spider_cgu):
        """Campos do documento (A2) devem ser corretamente mapeados no Item."""
        response = fake_response(
            "cgu/a2_response.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        items = _emenda_items(
            _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO))
        )
        primeiro = items[0]

        assert primeiro["codigo_documento"] == "2026NE456110"
        assert primeiro["fase_documento"] == "Empenho"
        assert primeiro["data_documento"] == "13/04/2026"
        assert "FUNDO MUNICIPAL DE SAUDE" in primeiro["favorecido"]
        assert primeiro["valor_documento"] == "500.000,00"

    def test_a2_vazio_nao_gera_items(self, spider_cgu):
        """A2 com data=[] não deve gerar nenhum EmendaParlamentarItem."""
        response = fake_response(
            "cgu/a2_empty.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        items = _emenda_items(
            _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO))
        )
        assert len(items) == 0

    def test_json_invalido_no_a2_nao_causa_excecao(self, spider_cgu):
        """Payload corrompido no A2 deve logar erro e retornar sem levantar exceção."""
        import scrapy.http

        bad_request = scrapy.http.Request(
            url="https://portaldatransparencia.gov.br/fake-a2",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        bad_response = scrapy.http.TextResponse(
            url="https://portaldatransparencia.gov.br/fake-a2",
            body=b"<html>Erro 503</html>",
            encoding="utf-8",
            request=bad_request,
        )
        results = _collect(spider_cgu.parse_documentos(bad_response, _DADOS_A1_EXEMPLO))
        assert results == []


# ---------------------------------------------------------------------------
# Grupo 4 — parse_emendas com código inválido
# ---------------------------------------------------------------------------

class TestParseEmendasComCodigoInvalido:
    """
    Verifica que emendas com codigoEmenda não-numérico ('S/I', 'REL. GERAL') são
    descartadas antes de disparar qualquer requisição ao A2.

    Fixture a1_com_emenda_invalida.json contém 3 emendas:
      - "202639000008" (válida)  → deve gerar 1 request A2
      - "S/I"                   → deve ser ignorada
      - "REL. GERAL"            → deve ser ignorada
    """

    def test_emenda_valida_gera_request_a2(self, spider_cgu):
        """A emenda com código numérico válido deve gerar exatamente 1 request A2."""
        response = fake_response("cgu/a1_com_emenda_invalida.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a2_requests = [r for r in _requests(results) if BASE_A2 in r.url]
        assert len(a2_requests) == 1

    def test_emenda_si_nao_gera_request_a2(self, spider_cgu):
        """Emenda com codigoEmenda='S/I' não deve gerar request ao A2."""
        response = fake_response("cgu/a1_com_emenda_invalida.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a2_requests = [r for r in _requests(results) if BASE_A2 in r.url]
        # Apenas 1 request A2 (a emenda válida) — S/I e REL. GERAL descartadas
        assert len(a2_requests) == 1

    def test_codigo_invalido_nao_contamina_url_a2(self, spider_cgu):
        """A URL do request A2 gerado deve conter o código numérico válido, não S/I."""
        response = fake_response("cgu/a1_com_emenda_invalida.json", meta={"offset": 0})
        results = _collect(spider_cgu.parse_emendas(response))
        a2_requests = [r for r in _requests(results) if BASE_A2 in r.url]
        assert "202639000008" in a2_requests[0].url
        assert "S%2FI" not in a2_requests[0].url   # "S/I" URL-encoded
        assert "REL." not in a2_requests[0].url


# ---------------------------------------------------------------------------
# Grupo 5 — paginação do A2
# ---------------------------------------------------------------------------

class TestParseDocumentosPaginacao:
    """
    Verifica que parse_documentos pagina o A2 corretamente quando recordsTotal
    ultrapassa o tamanho de uma página (PAGE_SIZE_A2=1000).

    Contexto: análise do dump 2018-2026 identificou 230 emendas com >=1000 docs,
    sendo o máximo 403.000 (truncamento confirmado). Emendas de Relator
    (sk_tipo_emenda=5) são as mais afetadas por terem muitos beneficiários municipais.

    Fixture a2_paginado.json: recordsTotal=2000, 2 docs na página (offset=0).
    """

    def test_pagina_quando_records_total_maior_que_page_size(self, spider_cgu):
        """recordsTotal=2000 com offset=0 deve gerar items + 1 request de próxima página."""
        response = fake_response(
            "cgu/a2_paginado.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        results = _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO, offset_a2=0))
        a2_next = [r for r in _requests(results) if BASE_A2 in r.url]
        items = _emenda_items(results)
        assert len(items) == 2, "Deve gerar 2 items da página atual"
        assert len(a2_next) == 1, "Deve gerar 1 request para a próxima página"

    def test_proximo_offset_a2_e_incrementado_corretamente(self, spider_cgu):
        """O offset do próximo request A2 deve ser offset_atual + PAGE_SIZE_A2."""
        response = fake_response(
            "cgu/a2_paginado.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        results = _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO, offset_a2=0))
        a2_next = [r for r in _requests(results) if BASE_A2 in r.url]
        assert "offset=1000" in a2_next[0].url

    def test_nao_pagina_quando_ultima_pagina(self, spider_cgu):
        """Na última página (offset=1000, total=2000), não deve gerar novo request A2."""
        response = fake_response(
            "cgu/a2_paginado.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        # offset_a2=1000 + PAGE_SIZE_A2=1000 = 2000, que não é < recordsTotal=2000
        results = _collect(
            spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO, offset_a2=1000)
        )
        a2_next = [r for r in _requests(results) if BASE_A2 in r.url]
        assert len(a2_next) == 0

    def test_items_gerados_mesmo_com_paginacao_pendente(self, spider_cgu):
        """Items da página atual devem ser gerados independentemente de haver próxima página."""
        response = fake_response(
            "cgu/a2_paginado.json",
            cb_kwargs={"dados_a1": _DADOS_A1_EXEMPLO},
        )
        results = _collect(spider_cgu.parse_documentos(response, _DADOS_A1_EXEMPLO, offset_a2=0))
        items = _emenda_items(results)
        assert all(isinstance(i, EmendaParlamentarItem) for i in items)
        assert items[0]["codigo_documento"] == "2021NE123456"
        assert items[1]["codigo_documento"] == "2021OB654321"
