"""
Spider: EmendasParlamentaresSpider

Responsável exclusivamente pela orquestração HTTP:
  - Disparar requisições paginadas ao endpoint A1
  - Para cada emenda, disparar requisição ao endpoint A2
  - Delegar extração e construção de itens ao CguEmendasCollector

Fluxo de dados:
  [A1] /emendas/consulta/resultado  →  todos os tipos de emenda (sem filtro)
       ↓  codigoEmenda (chave primária)
  [A2] /emendas/documentos-relacionados/resultado  →  todos os documentos relacionados
       ↓
  EmendaParlamentarItem consolidado (autor, emenda, documento, favorecido, valor, data)

Granularidade de saída: um item por documento (OB, NE, NS) por emenda.
"""

import datetime
from urllib.parse import urlencode

import scrapy
from mutuca.core.cgu_emendas_collector import CguEmendasCollector
from mutuca.utils.error_handlers import handle_request_error
from mutuca.utils.logger import get_logger

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
BASE_A1 = "https://portaldatransparencia.gov.br/emendas/consulta/resultado"
BASE_A2 = (
    "https://portaldatransparencia.gov.br/emendas/documentos-relacionados/resultado"
)

# ---------------------------------------------------------------------------
# Paginação
# ---------------------------------------------------------------------------
PAGE_SIZE_A1 = 1000  # blocos reais de paginação do A1
PAGE_SIZE_A2 = 1000  # traz todos os documentos de uma emenda de uma vez

# ---------------------------------------------------------------------------
# Colunas solicitadas à API (conforme contrato da CGU)
# ---------------------------------------------------------------------------
COLUNAS_A1 = (
    "linkDetalhamento,ano,tipoEmenda,autor,numeroEmenda,"
    "possuiApoiadorSolicitante,localidadeDoGasto,funcao,subfuncao,"
    "programa,acao,planoOrcamentario,codigoEmenda,valorEmpenhado,"
    "valorLiquidado,valorPago,valorRestoInscrito,valorRestoCancelado,valorRestoPago"
)


class EmendasParlamentaresSpider(scrapy.Spider):
    name = "emendas_parlamentares"
    custom_settings = {
        "FEEDS": {
            "emendas_parlamentares_%(data_inicio)s_%(data_fim)s.json": {
                "format": "json"
            }
        },
    }

    def __init__(self, de=None, ate=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_atual = str(datetime.date.today().year)
        self.data_inicio = de or ano_atual
        self.data_fim = ate or ano_atual
        self.log = get_logger(self.name)
        self.collector = CguEmendasCollector()

    # ---------------------------------------------------------------------------
    # Parâmetros base do A1 (offset é sobrescrito em cada requisição)
    # ---------------------------------------------------------------------------
    @property
    def _params_a1_base(self) -> dict:
        return {
            "paginacaoSimples": "false",
            "tamanhoPagina": str(PAGE_SIZE_A1),
            "offset": "0",
            "direcaoOrdenacao": "asc",
            "colunaOrdenacao": "autor",
            "de": self.data_inicio,
            "ate": self.data_fim,
            "colunasSelecionadas": COLUNAS_A1,
        }

    # ---------------------------------------------------------------------------
    # Ponto de entrada
    # ---------------------------------------------------------------------------
    def start_requests(self):
        params = {**self._params_a1_base, "offset": "0"}
        url = f"{BASE_A1}?{urlencode(params)}"

        self.log.info(
            f"Iniciando raspagem A1 | de={self.data_inicio} ate={self.data_fim} | offset=0"
        )

        yield scrapy.Request(
            url=url,
            callback=self.parse_emendas,
            meta={"offset": 0},
            errback=lambda f: handle_request_error(f, self.log),
        )

    # ---------------------------------------------------------------------------
    # Callback A1: pagina o endpoint e despacha requisições ao A2
    # ---------------------------------------------------------------------------
    def parse_emendas(self, response):
        """
        Consome JSON do A1.
        1. Valida payload.
        2. Para cada emenda, delega extração ao collector e dispara request ao A2.
        3. Pagina o A1 enquanto offset < recordsTotal.
        """
        try:
            payload = response.json()
        except Exception as e:
            self.log.error(
                f"Falha ao decodificar JSON do A1: {e} | URL: {response.url}"
            )
            return

        records_total = payload.get("recordsTotal", 0)
        emendas = payload.get("data", [])
        offset_atual = response.meta["offset"]

        self.log.info(
            f"A1 | offset={offset_atual} | total={records_total} | pagina={len(emendas)}"
        )

        for emenda in emendas:
            dados_a1 = self.collector.extrair_dados_a1(emenda)
            params_a2 = self.collector.montar_params_a2(
                dados_a1, page_size=PAGE_SIZE_A2
            )

            yield scrapy.Request(
                url=f"{BASE_A2}?{urlencode(params_a2)}",
                callback=self.parse_documentos,
                cb_kwargs={"dados_a1": dados_a1},
                errback=lambda f: handle_request_error(f, self.log),
            )

        # Paginação do A1
        proximo_offset = offset_atual + PAGE_SIZE_A1
        if proximo_offset < records_total:
            params = {**self._params_a1_base, "offset": str(proximo_offset)}
            self.log.info(f"Paginando A1 -> offset={proximo_offset}/{records_total}")
            yield scrapy.Request(
                url=f"{BASE_A1}?{urlencode(params)}",
                callback=self.parse_emendas,
                meta={"offset": proximo_offset},
                errback=lambda f: handle_request_error(f, self.log),
            )
        else:
            self.log.info("A1 completamente percorrido.")

    # ---------------------------------------------------------------------------
    # Callback A2: delega construção do item ao collector
    # ---------------------------------------------------------------------------
    def parse_documentos(self, response, dados_a1: dict):
        """
        Consome JSON do A2.
        Relacionamento: dados_a1["codigo_emenda"] == parâmetro 'codigo' enviado ao A2.
        Faz yield de um EmendaParlamentarItem por documento, via collector.
        """
        try:
            payload = response.json()
        except Exception as e:
            self.log.error(
                f"Falha ao decodificar JSON do A2 para emenda "
                f"{dados_a1.get('codigo_emenda')}: {e}"
            )
            return

        documentos = payload.get("data", [])

        for doc in documentos:
            yield self.collector.construir_item(dados_a1, doc)

        self.log.info(
            f"Emenda {dados_a1['codigo_emenda']} → {len(documentos)} documento(s).",
            extra={
                "codigo_emenda": dados_a1["codigo_emenda"],
                "documentos": len(documentos),
            },
        )
