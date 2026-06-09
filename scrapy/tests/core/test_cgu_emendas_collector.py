"""
Testes unitários — CguEmendasCollector

Testa os quatro métodos públicos do collector de forma completamente isolada:
sem Scrapy, sem fixtures JSON, sem HTTP. Entrada e saída são dicts e Items puros.

Classes de teste:
  TestCodigoEmendaValido   — validação de códigos numéricos vs não-numéricos (S/I, REL. GERAL)
  TestExtrairDadosA1       — mapeamento camelCase → snake_case dos campos do endpoint A1
  TestMontarParamsA2       — construção dos parâmetros de query para o endpoint A2 (com offset)
  TestConstruirItem        — consolidação A1 + A2 → EmendaParlamentarItem

Contexto de TestCodigoEmendaValido:
  A análise empírica do dump 2018–2026 identificou emendas com codigoEmenda='S/I'
  (403.000 docs) e codigoEmenda='REL. GERAL' (124.000 docs). Esses valores fazem a
  API do A2 ignorar o filtro de código e retornar todos os documentos que casam com
  os demais parâmetros, contaminando a base. O método codigo_emenda_valido() bloqueia
  esse comportamento antes de qualquer requisição ao A2.

Execução:
    cd scrapy/
    pytest tests/core/test_cgu_emendas_collector.py -v
"""

import pytest

from mutuca.core.cgu_emendas_collector import CguEmendasCollector
from mutuca.items.cgu_emendas_item import EmendaParlamentarItem

# ---------------------------------------------------------------------------
# Payloads de entrada que simulam o formato camelCase da API CGU
# ---------------------------------------------------------------------------

EMENDA_A1_RAW = {
    "autor": "3900 - ADRIANO DO BALDY",
    "codigoEmenda": "202639000008",
    "tipoEmenda": "Emenda Individual - Transferências com Finalidade Definida",
    "skTipoEmenda": 2,
    "localidadeDoGasto": "MÚLTIPLO",
    "codigoFuncao": "10",
    "funcao": "Saúde",
    "codigoSubfuncao": "302",
    "subfuncao": "Assistência hospitalar e ambulatorial",
    "programa": "5118 - ATENCAO ESPECIALIZADA A SAUDE",
    "acao": "2E90 - INCREMENTO TEMPORARIO AO CUSTEIO DOS SERVICOS",
    "planoOrcamentario": "INCREMENTO TEMPORARIO AO CUSTEIO DOS SERVICOS",
    "numeroEmenda": "0008",
    "ano": 2026,
    "valorPago": "1.653.375,00",
    "valorEmpenhado": "3.053.375,00",
    "valorLiquidado": "1.653.375,00",
    "valorRestoInscrito": "0,00",
    "valorRestoCancelado": "0,00",
    "valorRestoPago": "0,00",
    "possuiApoiadorSolicitante": "Não se aplica",
}

DOC_A2_RAW = {
    "codigoDocumentoResumido": "2026NE456110",
    "fase": "Empenho",
    "data": "13/04/2026",
    "favorecido": "04.786.328/0001-36 - FUNDO MUNICIPAL DE SAUDE",
    "valor": "500.000,00",
}


@pytest.fixture
def collector():
    return CguEmendasCollector()


@pytest.fixture
def dados_a1(collector):
    """Saída normalizada de extrair_dados_a1 — base para os demais testes."""
    return collector.extrair_dados_a1(EMENDA_A1_RAW)


# ---------------------------------------------------------------------------
# codigo_emenda_valido
# ---------------------------------------------------------------------------

class TestCodigoEmendaValido:
    """
    Valida o filtro que impede emendas com codigoEmenda não-numérico de disparar
    requisições ao A2. Contexto: dump 2018-2026 revelou 'S/I' com 403.000 docs
    e 'REL. GERAL' com 124.000 docs — resultados inflados por falha de filtro na API.
    """

    def test_codigo_numerico_12_digitos_e_valido(self, collector):
        assert collector.codigo_emenda_valido("202639000008") is True

    def test_codigo_numerico_10_digitos_e_valido(self, collector):
        """Intervalo mínimo: alguns tipos de emenda usam códigos mais curtos."""
        assert collector.codigo_emenda_valido("2026390008") is True

    def test_codigo_si_e_invalido(self, collector):
        """'S/I' (Sem Informação) — emenda de comissão sem código individual."""
        assert collector.codigo_emenda_valido("S/I") is False

    def test_codigo_rel_geral_e_invalido(self, collector):
        """'REL. GERAL' — relatoria geral de comissão sem código numérico."""
        assert collector.codigo_emenda_valido("REL. GERAL") is False

    def test_codigo_vazio_e_invalido(self, collector):
        assert collector.codigo_emenda_valido("") is False

    def test_codigo_none_e_invalido(self, collector):
        assert collector.codigo_emenda_valido(None) is False


# ---------------------------------------------------------------------------
# extrair_dados_a1
# ---------------------------------------------------------------------------

class TestExtrairDadosA1:

    def test_retorna_dict(self, collector):
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert isinstance(resultado, dict)

    def test_mapeia_codigo_emenda(self, collector):
        """codigoEmenda (camelCase) → codigo_emenda (snake_case)."""
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert resultado["codigo_emenda"] == "202639000008"

    def test_mapeia_autor(self, collector):
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert resultado["autor"] == "3900 - ADRIANO DO BALDY"

    def test_mapeia_valor_pago_para_valor_total_a1(self, collector):
        """valorPago do A1 deve ser mapeado para valor_total_a1 (não valor_pago)."""
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert resultado["valor_total_a1"] == "1.653.375,00"

    def test_mapeia_todos_os_campos_de_valor(self, collector):
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert resultado["valor_empenhado"] == "3.053.375,00"
        assert resultado["valor_liquidado"] == "1.653.375,00"
        assert resultado["valor_resto_inscrito"] == "0,00"
        assert resultado["valor_resto_cancelado"] == "0,00"
        assert resultado["valor_resto_pago"] == "0,00"

    def test_mapeia_sk_tipo_emenda(self, collector):
        """skTipoEmenda é necessário como parâmetro de filtro no A2."""
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert resultado["sk_tipo_emenda"] == 2

    def test_campo_ausente_retorna_string_vazia(self, collector):
        """Campo inexistente no payload deve retornar '' (não None nem KeyError)."""
        resultado = collector.extrair_dados_a1({})
        assert resultado["codigo_emenda"] == ""
        assert resultado["autor"] == ""

    def test_subfuncao_ausente_retorna_none(self, collector):
        """subfuncao usa .get() sem default — pode ser None se ausente."""
        resultado = collector.extrair_dados_a1({})
        assert resultado["subfuncao"] is None

    def test_contem_todos_os_21_campos(self, collector):
        resultado = collector.extrair_dados_a1(EMENDA_A1_RAW)
        assert len(resultado) == 21


# ---------------------------------------------------------------------------
# montar_params_a2
# ---------------------------------------------------------------------------

class TestMontarParamsA2:

    def test_retorna_dict(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1)
        assert isinstance(params, dict)

    def test_codigo_emenda_vira_parametro_codigo(self, collector, dados_a1):
        """codigo_emenda deve ir como 'codigo' na query string do A2."""
        params = collector.montar_params_a2(dados_a1)
        assert params["codigo"] == "202639000008"

    def test_sk_tipo_emenda_preservado(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1)
        assert params["skTipoEmenda"] == 2

    def test_page_size_padrao_e_1000(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1)
        assert params["tamanhoPagina"] == "1000"

    def test_page_size_customizavel(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1, page_size=500)
        assert params["tamanhoPagina"] == "500"

    def test_offset_inicial_e_zero(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1)
        assert params["offset"] == "0"

    def test_offset_customizavel(self, collector, dados_a1):
        """
        Paginação do A2: offset deve ser transmitido como string para o urlencode.
        Emendas de Relator (sk_tipo_emenda=5) podem ter mais de 1000 documentos —
        cada página subsequente usa offset incrementado por PAGE_SIZE_A2.
        """
        params = collector.montar_params_a2(dados_a1, offset=1000)
        assert params["offset"] == "1000"

    def test_colunas_a2_presentes(self, collector, dados_a1):
        params = collector.montar_params_a2(dados_a1)
        assert "colunasSelecionadas" in params
        assert "favorecido" in params["colunasSelecionadas"]


# ---------------------------------------------------------------------------
# construir_item
# ---------------------------------------------------------------------------

class TestConstruirItem:

    def test_retorna_emenda_parlamentar_item(self, collector, dados_a1):
        item = collector.construir_item(dados_a1, DOC_A2_RAW)
        assert isinstance(item, EmendaParlamentarItem)

    def test_campos_a1_propagados(self, collector, dados_a1):
        item = collector.construir_item(dados_a1, DOC_A2_RAW)
        assert item["autor"] == "3900 - ADRIANO DO BALDY"
        assert item["codigo_emenda"] == "202639000008"
        assert item["funcao"] == "Saúde"
        assert item["ano"] == 2026
        assert item["valor_empenhado"] == "3.053.375,00"

    def test_campos_a2_mapeados(self, collector, dados_a1):
        """Chaves camelCase do A2 devem ser convertidas para snake_case no item."""
        item = collector.construir_item(dados_a1, DOC_A2_RAW)
        assert item["codigo_documento"] == "2026NE456110"
        assert item["fase_documento"] == "Empenho"
        assert item["data_documento"] == "13/04/2026"
        assert item["favorecido"] == "04.786.328/0001-36 - FUNDO MUNICIPAL DE SAUDE"
        assert item["valor_documento"] == "500.000,00"

    def test_data_extracao_preenchida(self, collector, dados_a1):
        item = collector.construir_item(dados_a1, DOC_A2_RAW)
        assert item["data_extracao"]

    def test_data_extracao_e_iso8601(self, collector, dados_a1):
        """data_extracao deve ser um timestamp ISO 8601 parseável."""
        from datetime import datetime
        item = collector.construir_item(dados_a1, DOC_A2_RAW)
        # Não deve lançar ValueError
        datetime.fromisoformat(item["data_extracao"])

    def test_doc_vazio_preenche_campos_a2_com_string_vazia(self, collector, dados_a1):
        """Documento A2 sem campos deve gerar item com strings vazias, sem KeyError."""
        item = collector.construir_item(dados_a1, {})
        assert item["codigo_documento"] == ""
        assert item["fase_documento"] == ""
        assert item["favorecido"] == ""
