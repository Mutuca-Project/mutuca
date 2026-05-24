"""
Spider: EmendasParlamentaresSpider 

Coleta dados de emendas parlamentares do portal da transparência da Controladoria Geral 
da União.

Fluxo de dados:
  [A1] /emendas/consulta/resultado  →  todos os tipos de emenda (sem filtro)
       ↓  codigoEmenda (chave primária)
  [A2] /emendas/documentos-relacionados/resultado  →  todos os documentos relacionados
       ↓
  Item consolidado (autor, emenda, documento, favorecido, valor, data)
"""

import datetime
from urllib.parse import urlencode

import scrapy

BASE_A1 = "https://portaldatransparencia.gov.br/emendas/consulta/resultado"

BASE_A2 = (
    "https://portaldatransparencia.gov.br/emendas/documentos-relacionados/resultado"
)

# Tamanho de página do A1 (paginação real em blocos de 1000)
PAGE_SIZE_A1 = 1000

# Tamanho de página do A2 — traz TODOS os documentos de uma emenda de uma vez
PAGE_SIZE_A2 = 1000

# Colunas permitidas para envio
COLUNAS_SELECIONADAS_A1 = (
    "linkDetalhamento,ano,tipoEmenda,autor,numeroEmenda,"
    "possuiApoiadorSolicitante,localidadeDoGasto,funcao,subfuncao,"
    "programa,acao,planoOrcamentario,codigoEmenda,valorEmpenhado,"
    "valorLiquidado,valorPago,valorRestoInscrito,valorRestoCancelado,valorRestoPago"
)

COLUNAS_SELECIONADAS_A2 = "data,fase,codigoDocumentoResumido,favorecido,valor"


class EmedasParlamentaresSpider(scrapy.Spider):
    name = "emendas_parlamentares"
    custom_settings = {
        "FEEDS": {"emendas_parlamentares_2018_2026.json": {"format": "json"}},
    }

    def __init__(self, de=None, ate=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_atual = str(datetime.date.today().year)
        self.data_inicio = de or ano_atual
        self.data_fim = ate or ano_atual

    # ----------------------------------------------------------------------------------------
    # Parâmetros base do Endpoint para A1
    # Mantidos conforme padrão da CGU; offset será incrementado em parse_emendas
    # ----------------------------------------------------------------------------------------
    @property
    def _params_a1_base(self):
        return {
            "paginacaoSimples": "false",
            "tamanhoPagina": str(PAGE_SIZE_A1),
            "offset": "0",
            "direcaoOrdenacao": "asc",
            "colunaOrdenacao": "autor",
            "de": self.data_inicio,
            "ate": self.data_fim,
            "colunasSelecionadas": COLUNAS_SELECIONADAS_A1,
        }

    # ----------------------------------------------------------------------------------------
    # Ponto de entrada: dispara a primeira requisição ao A1 (offset=0)
    # ----------------------------------------------------------------------------------------

    def start_requests(self):
        params = {**self._params_a1_base, "offset": "0"}
        url = f"{BASE_A1}?{urlencode(params)}"

        self.logger.info("Iniciando raspagem do A1 - offset=0")

        yield scrapy.Request(
            url=url,
            callback=self.parse_emendas,
            meta={"offset": 0},
            errback=self.handle_error,
        )

    # ----------------------------------------------------------------------------------------
    # Callback A1: processa lista de emendas e dispara requisições ao A2
    # ----------------------------------------------------------------------------------------

    def parse_emendas(self, response):
        """
        Consome a resposta JSON do Endpoint A1.

        1. Valida o payload.
        2. Para cada emenda (todos os tipos), dispara requisição ao A2
        3. Implementa paginação: enquanto offset < recordsTotal, dispara nova requisição ao A1
           com offset incrementado
        """
        try:
            payload = response.json()
        except Exception as e:
            self.logger.error(
                f"Falha ao decodificar JSON do A1: {e} | URL: {response.url}"
            )
            return

        records_total = payload.get("recordsTotal", 0)
        emendas = payload.get("data", [])
        offset_atual = response.meta["offset"]

        self.logger.info(
            f"A1 | offset={offset_atual} | total={records_total} | "
            f"emendas_na_pagina={len(emendas)}"
        )

        # ------------------------------------------------------------------------------------
        # Itera todas as emendas sem filtro de tipo
        # ------------------------------------------------------------------------------------
        for emenda in emendas:
            # Dados extraídos de A1 que serão unidos ao payload de A2
            dados_a1 = {
                "autor": emenda.get("autor", ""),
                "codigo_emenda": emenda.get("codigoEmenda", ""),
                "tipo_emenda": emenda.get("tipoEmenda", ""),
                "sk_tipo_emenda": emenda.get("skTipoEmenda", ""),
                "localidade_do_gasto": emenda.get("localidadeDoGasto", ""),
                "codigo_funcao": emenda.get("codigoFuncao", ""),
                "funcao": emenda.get("funcao", ""),
                "codigo_subfuncao": emenda.get("codigoSubfuncao", ""),
                "subfuncao": emenda.get("subfuncao"),
                "programa": emenda.get("programa", ""),
                "acao": emenda.get("acao", ""),
                "plano_orcamentario": emenda.get("planoOrcamentario", ""),
                "numero_emenda": emenda.get("numeroEmenda", ""),
                "ano": emenda.get("ano", ""),
                "valor_total_a1": emenda.get("valorPago", ""),
                "valor_empenhado": emenda.get("valorEmpenhado", ""),
                "valor_liquidado": emenda.get("valorLiquidado", ""),
                "valor_resto_inscrito": emenda.get("valorRestoInscrito", ""),
                "valor_resto_cancelado": emenda.get("valorRestoCancelado", ""),
                "valor_resto_pago": emenda.get("valorRestoPago", ""),
                "possui_apoio_solicitante": emenda.get("possuiApoiadorSolicitante", ""),
            }

            # Monda a URL do A2 usando codigoEmenda como chave primária de relacionamento
            params_a2 = {
                "paginacaoSimples": "false",
                "tamanhoPagina": str(PAGE_SIZE_A2),
                "offset": "0",
                "direcaoOrdenacao": "asc",
                "colunaOrdenacao": "data",
                "colunasSelecionadas": COLUNAS_SELECIONADAS_A2,
                "codigo": dados_a1["codigo_emenda"],  # ← chave do relacionamento A1→A2
                "ano": dados_a1["ano"],
                "codigoFuncao": dados_a1["codigo_funcao"],
                "codigoSubfuncao": dados_a1["codigo_subfuncao"],
                "localidadeDoGasto": dados_a1["localidade_do_gasto"],
                "skTipoEmenda": dados_a1["sk_tipo_emenda"],
                "palavraChave": "",
            }

            url_a2 = f"{BASE_A2}?{urlencode(params_a2)}"

            yield scrapy.Request(
                url=url_a2,
                callback=self.parse_documentos,
                # cb_kwargs repassa os dados do A1 para o callback do A2
                cb_kwargs={"dados_a1": dados_a1},
                errback=self.handle_error,
            )

        # --------------------------------------------------------------------------------
        # Paginação do A1: dispara próximas páginas se ainda houver registros
        # --------------------------------------------------------------------------------
        proximo_offset = offset_atual + PAGE_SIZE_A1

        if proximo_offset < records_total:
            params = {**self._params_a1_base, "offset": str(proximo_offset)}
            url_proxima = f"{BASE_A1}?{urlencode(params)}"

            self.logger.debug(
                f"Paginando A1 -> offset={proximo_offset}/{records_total}"
            )

            yield scrapy.Request(
                url=url_proxima,
                callback=self.parse_emendas,
                meta={"offset": proximo_offset},
                errback=self.handle_error,
            )
        else:
            self.logger.info("A1 completamente percorrido - sem mais páginas")

    def parse_documentos(self, response, dados_a1: dict):
        """
        Consome a resposta JSON do Endpoit A2.

        Relacionamento com A1:
            dados_a1["codigo_emenda"] == parâmetro 'codigo' enviado ao A2.

        Faz yield de um item consolidado para CADA documento retornado (OB, NE, NS) - a
        didtinção por fase é responsabilidade da camada Silver.
        """

        try:
            payload = response.json()
        except Exception as e:
            self.logger.error(
                f"Falha ao decodificar JSON do A2 para emenda "
                f"{dados_a1.get('codigo_emenda')}: {e}"
            )
            return

        documentos = payload.get("data", [])

        for doc in documentos:
            # Item final: junção dos campos A1 e A2

            yield {
                # Campos oriundos do Endpoint A1
                "autor": dados_a1["autor"],
                "codigo_emenda": dados_a1["codigo_emenda"],
                "tipo_emenda": dados_a1["tipo_emenda"],
                "sk_tipo_emenda": dados_a1["sk_tipo_emenda"],
                "localidade_do_gasto": dados_a1["localidade_do_gasto"],
                "codigo_funcao": dados_a1["codigo_funcao"],
                "funcao": dados_a1["funcao"],
                "codigo_subfuncao": dados_a1["codigo_subfuncao"],
                "subfuncao": dados_a1["subfuncao"],
                "programa": dados_a1["programa"],
                "acao": dados_a1["acao"],
                "plano_orcamentario": dados_a1["plano_orcamentario"],
                "numero_emenda": dados_a1["numero_emenda"],
                "ano": dados_a1["ano"],
                "valor_total_a1": dados_a1["valor_total_a1"],
                "valor_empenhado": dados_a1["valor_empenhado"],
                "valor_liquidado": dados_a1["valor_liquidado"],
                "valor_resto_inscrito": dados_a1["valor_resto_inscrito"],
                "valor_resto_cancelado": dados_a1["valor_resto_cancelado"],
                "valor_resto_pago": dados_a1["valor_resto_pago"],
                "possui_apoio_solicitante": dados_a1["possui_apoio_solicitante"],
                # Campos oriundos do Endpoint A2
                "codigo_documento": doc.get("codigoDocumentoResumido", ""),
                "fase_documento": doc.get("fase", ""),
                "data_documento": doc.get("data", ""),
                "favorecido": doc.get("favorecido", ""),
                "valor_documento": doc.get("valor", ""),
            }

        self.logger.debug(
            f"Emenda {dados_a1['codigo_emenda']} = {len(documentos)} documento(s) gravado(s)."
        )

    # Tratamento de erros
    def handle_error(self, failure):
        self.logger.error(
            f"Erro na requisição: {failure.request.url} | " f"{repr(failure.value)}"
        )
