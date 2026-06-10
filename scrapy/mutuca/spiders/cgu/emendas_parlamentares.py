"""
Spider: EmendasParlamentaresSpider

Responsável exclusivamente pela orquestração HTTP:
  - Disparar requisições paginadas ao endpoint A1
  - Para cada emenda, validar código e disparar requisição paginada ao A2
  - Delegar extração e construção de itens ao CguEmendasCollector

Fluxo de dados:
  [A1] /emendas/consulta/resultado  →  todos os tipos de emenda (sem filtro)
       ↓  validação de codigoEmenda (filtra S/I, REL. GERAL e similares)
       ↓  codigoEmenda numérico válido
  [A2] /emendas/documentos-relacionados/resultado  →  documentos paginados
       ↓  paginação até esgotar recordsTotal
  EmendaParlamentarItem consolidado (autor, emenda, documento, favorecido, valor, data)

Granularidade de saída: um item por documento (OB, NE, NS) por emenda.

Decisões de design documentadas:
  - Emendas com codigoEmenda não-numérico ('S/I', 'REL. GERAL') são ignoradas antes
    de disparar qualquer requisição ao A2. Sem esse filtro, a API retorna até 403.000
    documentos por emenda ao ignorar o filtro de código inválido. Ver CguEmendasCollector.
  - O endpoint A2 é paginado da mesma forma que o A1. Emendas de Relator
    (sk_tipo_emenda=5) podem ultrapassar 1.000 documentos. Sem paginação, os
    documentos excedentes seriam descartados silenciosamente.
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
PAGE_SIZE_A1 = 1000  # blocos de paginação do A1
PAGE_SIZE_A2 = 1000  # blocos de paginação do A2

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
        # Formato jsonlines (um objeto JSON por linha) exigido pelo iceberg_loader.
        # Em produção (Airflow), este FEEDS é ignorado — o output é controlado
        # pelo campo scrapy.output do cgu.yaml via flag -O.
        "FEEDS": {
            "emendas_parlamentares_%(data_inicio)s_%(data_fim)s.jsonl": {
                "format": "jsonlines"
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
    # Callback A1: valida códigos, pagina o endpoint e despacha requisições ao A2
    # ---------------------------------------------------------------------------
    def parse_emendas(self, response):
        """
        Consome JSON do A1.
        1. Valida payload.
        2. Para cada emenda, verifica se o codigoEmenda é numérico válido.
           Emendas com código inválido (S/I, REL. GERAL) são ignoradas com log.
        3. Delega extração ao collector e dispara request ao A2 (offset=0).
        4. Pagina o A1 enquanto offset < recordsTotal.
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

            if not self.collector.codigo_emenda_valido(dados_a1["codigo_emenda"]):
                self.log.warning(
                    f"Emenda ignorada — código inválido: '{dados_a1['codigo_emenda']}' "
                    f"| tipo: {dados_a1['tipo_emenda']}",
                    extra={
                        "codigo_emenda": dados_a1["codigo_emenda"],
                        "tipo_emenda": dados_a1["tipo_emenda"],
                        "sk_tipo_emenda": dados_a1["sk_tipo_emenda"],
                    },
                )
                continue

            params_a2 = self.collector.montar_params_a2(
                dados_a1, page_size=PAGE_SIZE_A2, offset=0
            )

            yield scrapy.Request(
                url=f"{BASE_A2}?{urlencode(params_a2)}",
                callback=self.parse_documentos,
                cb_kwargs={"dados_a1": dados_a1, "offset_a2": 0},
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
    # Callback A2: gera items e pagina se necessário
    # ---------------------------------------------------------------------------
    def parse_documentos(self, response, dados_a1: dict, offset_a2: int = 0):
        """
        Consome JSON do A2 para uma página específica.
        Relacionamento: dados_a1["codigo_emenda"] == parâmetro 'codigo' enviado ao A2.

        Para cada documento na página, faz yield de um EmendaParlamentarItem via collector.
        Se ainda houver documentos (offset_a2 + PAGE_SIZE_A2 < recordsTotal), despacha
        a próxima página com offset incrementado — mesmo padrão da paginação do A1.
        """
        try:
            payload = response.json()
        except Exception as e:
            self.log.error(
                f"Falha ao decodificar JSON do A2 para emenda "
                f"{dados_a1.get('codigo_emenda')}: {e}"
            )
            return

        records_total = payload.get("recordsTotal", 0)
        documentos = payload.get("data", [])

        for doc in documentos:
            yield self.collector.construir_item(dados_a1, doc)

        # Paginação do A2
        proximo_offset_a2 = offset_a2 + PAGE_SIZE_A2
        if proximo_offset_a2 < records_total:
            params_a2 = self.collector.montar_params_a2(
                dados_a1, page_size=PAGE_SIZE_A2, offset=proximo_offset_a2
            )
            self.log.info(
                f"Paginando A2 para emenda {dados_a1['codigo_emenda']} "
                f"-> offset={proximo_offset_a2}/{records_total}",
                extra={
                    "codigo_emenda": dados_a1["codigo_emenda"],
                    "offset_a2": proximo_offset_a2,
                    "records_total": records_total,
                },
            )
            yield scrapy.Request(
                url=f"{BASE_A2}?{urlencode(params_a2)}",
                callback=self.parse_documentos,
                cb_kwargs={"dados_a1": dados_a1, "offset_a2": proximo_offset_a2},
                errback=lambda f: handle_request_error(f, self.log),
            )
        else:
            self.log.info(
                f"Emenda {dados_a1['codigo_emenda']} → {records_total} documento(s) total.",
                extra={
                    "codigo_emenda": dados_a1["codigo_emenda"],
                    "total_documentos": records_total,
                },
            )
