"""
Spider: EmendasParlamentaresSpider

Coleta dados de emendas parlamentares do portal da transparência da Controladoria Geral
da União.

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

from mutuca.items.cgu_emendas_item import EmendaParlamentarItem
from mutuca.utils.error_handlers import handle_request_error
from mutuca.utils.logger import get_logger

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
BASE_A1 = "https://portaldatransparencia.gov.br/emendas/consulta/resultado"
BASE_A2 = "https://portaldatransparencia.gov.br/emendas/documentos-relacionados/resultado"

# ---------------------------------------------------------------------------
# Paginação
# ---------------------------------------------------------------------------
PAGE_SIZE_A1 = 1000   # blocos reais de paginação do A1
PAGE_SIZE_A2 = 1000   # traz todos os documentos de uma emenda de uma vez

# ---------------------------------------------------------------------------
# Colunas solicitadas à API (conforme contrato da CGU)
# ---------------------------------------------------------------------------
COLUNAS_A1 = (
    "linkDetalhamento,ano,tipoEmenda,autor,numeroEmenda,"
    "possuiApoiadorSolicitante,localidadeDoGasto,funcao,subfuncao,"
    "programa,acao,planoOrcamentario,codigoEmenda,valorEmpenhado,"
    "valorLiquidado,valorPago,valorRestoInscrito,valorRestoCancelado,valorRestoPago"
)
COLUNAS_A2 = "data,fase,codigoDocumentoResumido,favorecido,valor"


class EmendasParlamentaresSpider(scrapy.Spider):
    name = "emendas_parlamentares"
    custom_settings = {
        "FEEDS": {"emendas_parlamentares_%(de)s_%(ate)s.json": {"format": "json"}},
    }

    def __init__(self, de=None, ate=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_atual = str(datetime.date.today().year)
        self.data_inicio = de or ano_atual
        self.data_fim = ate or ano_atual
        self.log = get_logger(self.name)

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
    # Callback A1: processa lista de emendas e dispara requisições ao A2
    # ---------------------------------------------------------------------------
    def parse_emendas(self, response):
        """
        Consome JSON do A1.
        1. Valida payload.
        2. Para cada emenda dispara requisição ao A2.
        3. Pagina o A1 enquanto offset < recordsTotal.
        """
        try:
            payload = response.json()
        except Exception as e:
            self.log.error(f"Falha ao decodificar JSON do A1: {e} | URL: {response.url}")
            return

        records_total = payload.get("recordsTotal", 0)
        emendas = payload.get("data", [])
        offset_atual = response.meta["offset"]

        self.log.info(
            f"A1 | offset={offset_atual} | total={records_total} | pagina={len(emendas)}"
        )

        for emenda in emendas:
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

            params_a2 = {
                "paginacaoSimples": "false",
                "tamanhoPagina": str(PAGE_SIZE_A2),
                "offset": "0",
                "direcaoOrdenacao": "asc",
                "colunaOrdenacao": "data",
                "colunasSelecionadas": COLUNAS_A2,
                "codigo": dados_a1["codigo_emenda"],
                "ano": dados_a1["ano"],
                "codigoFuncao": dados_a1["codigo_funcao"],
                "codigoSubfuncao": dados_a1["codigo_subfuncao"],
                "localidadeDoGasto": dados_a1["localidade_do_gasto"],
                "skTipoEmenda": dados_a1["sk_tipo_emenda"],
                "palavraChave": "",
            }

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
    # Callback A2: consolida campos A1 + A2 num EmendaParlamentarItem
    # ---------------------------------------------------------------------------
    def parse_documentos(self, response, dados_a1: dict):
        """
        Consome JSON do A2.
        Relacionamento: dados_a1["codigo_emenda"] == parâmetro 'codigo' enviado ao A2.
        Faz yield de um EmendaParlamentarItem por documento retornado.
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
        data_extracao = datetime.datetime.utcnow().isoformat()

        for doc in documentos:
            yield EmendaParlamentarItem(
                # Campos do A1
                autor=dados_a1["autor"],
                codigo_emenda=dados_a1["codigo_emenda"],
                tipo_emenda=dados_a1["tipo_emenda"],
                sk_tipo_emenda=dados_a1["sk_tipo_emenda"],
                localidade_do_gasto=dados_a1["localidade_do_gasto"],
                codigo_funcao=dados_a1["codigo_funcao"],
                funcao=dados_a1["funcao"],
                codigo_subfuncao=dados_a1["codigo_subfuncao"],
                subfuncao=dados_a1["subfuncao"],
                programa=dados_a1["programa"],
                acao=dados_a1["acao"],
                plano_orcamentario=dados_a1["plano_orcamentario"],
                numero_emenda=dados_a1["numero_emenda"],
                ano=dados_a1["ano"],
                valor_total_a1=dados_a1["valor_total_a1"],
                valor_empenhado=dados_a1["valor_empenhado"],
                valor_liquidado=dados_a1["valor_liquidado"],
                valor_resto_inscrito=dados_a1["valor_resto_inscrito"],
                valor_resto_cancelado=dados_a1["valor_resto_cancelado"],
                valor_resto_pago=dados_a1["valor_resto_pago"],
                possui_apoio_solicitante=dados_a1["possui_apoio_solicitante"],
                # Campos do A2
                codigo_documento=doc.get("codigoDocumentoResumido", ""),
                fase_documento=doc.get("fase", ""),
                data_documento=doc.get("data", ""),
                favorecido=doc.get("favorecido", ""),
                valor_documento=doc.get("valor", ""),
                # Metadados
                data_extracao=data_extracao,
            )

        self.log.info(
            f"Emenda {dados_a1['codigo_emenda']} → {len(documentos)} documento(s).",
            extra={"codigo_emenda": dados_a1["codigo_emenda"], "documentos": len(documentos)},
        )
