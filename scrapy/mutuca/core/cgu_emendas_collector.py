"""
CguEmendasCollector

Responsável pela transformação de dados brutos da API da CGU em estruturas
utilizáveis pelo pipeline. Contém toda a lógica de mapeamento de campos e
construção de itens, mantendo o spider focado exclusivamente na orquestração HTTP.

Métodos públicos (funções puras — dict/item entra, dict/item sai):
  - extrair_dados_a1(emenda)      → dict com campos normalizados do endpoint A1
  - montar_params_a2(dados_a1)    → dict com parâmetros prontos para a requisição A2
  - construir_item(dados_a1, doc) → EmendaParlamentarItem consolidado

Referência de campos:
  A1 (chaves camelCase da API → snake_case interno):
    codigoEmenda          → codigo_emenda   (chave primária do relacionamento A1→A2)
    autor                 → autor
    tipoEmenda            → tipo_emenda
    skTipoEmenda          → sk_tipo_emenda  (usado como parâmetro de filtro no A2)
    localidadeDoGasto     → localidade_do_gasto
    codigoFuncao          → codigo_funcao
    funcao                → funcao
    codigoSubfuncao       → codigo_subfuncao
    subfuncao             → subfuncao
    programa              → programa
    acao                  → acao
    planoOrcamentario     → plano_orcamentario
    numeroEmenda          → numero_emenda
    ano                   → ano
    valorPago             → valor_total_a1
    valorEmpenhado        → valor_empenhado
    valorLiquidado        → valor_liquidado
    valorRestoInscrito    → valor_resto_inscrito
    valorRestoCancelado   → valor_resto_cancelado
    valorRestoPago        → valor_resto_pago
    possuiApoiadorSolicitante → possui_apoio_solicitante

  A2 (chaves camelCase da API → campos do item):
    codigoDocumentoResumido → codigo_documento
    fase                    → fase_documento  (OB | NE | NS)
    data                    → data_documento
    favorecido              → favorecido      (CNPJ + nome do beneficiário)
    valor                   → valor_documento
"""

import datetime
from typing import Any

from mutuca.items.cgu_emendas_item import EmendaParlamentarItem
from mutuca.utils.logger import get_logger

logger = get_logger(__name__)


class CguEmendasCollector:
    """
    Transforma dados brutos da API de emendas parlamentares da CGU em
    estruturas normalizadas e itens Scrapy.

    Instanciar uma vez por spider; os métodos são stateless e thread-safe.
    """

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def extrair_dados_a1(self, emenda: dict) -> dict:
        """
        Mapeia os campos camelCase do payload A1 para snake_case normalizado.

        Args:
            emenda: Objeto de uma emenda conforme retornado pelo endpoint A1
                    (/emendas/consulta/resultado).

        Returns:
            Dicionário com campos normalizados, pronto para ser repassado como
            cb_kwargs ao request do A2 e ao método construir_item.
        """
        dados = {
            "autor":                  emenda.get("autor", ""),
            "codigo_emenda":          emenda.get("codigoEmenda", ""),
            "tipo_emenda":            emenda.get("tipoEmenda", ""),
            "sk_tipo_emenda":         emenda.get("skTipoEmenda", ""),
            "localidade_do_gasto":    emenda.get("localidadeDoGasto", ""),
            "codigo_funcao":          emenda.get("codigoFuncao", ""),
            "funcao":                 emenda.get("funcao", ""),
            "codigo_subfuncao":       emenda.get("codigoSubfuncao", ""),
            "subfuncao":              emenda.get("subfuncao"),
            "programa":               emenda.get("programa", ""),
            "acao":                   emenda.get("acao", ""),
            "plano_orcamentario":     emenda.get("planoOrcamentario", ""),
            "numero_emenda":          emenda.get("numeroEmenda", ""),
            "ano":                    emenda.get("ano", ""),
            "valor_total_a1":         emenda.get("valorPago", ""),
            "valor_empenhado":        emenda.get("valorEmpenhado", ""),
            "valor_liquidado":        emenda.get("valorLiquidado", ""),
            "valor_resto_inscrito":   emenda.get("valorRestoInscrito", ""),
            "valor_resto_cancelado":  emenda.get("valorRestoCancelado", ""),
            "valor_resto_pago":       emenda.get("valorRestoPago", ""),
            "possui_apoio_solicitante": emenda.get("possuiApoiadorSolicitante", ""),
        }

        logger.info(
            f"Dados A1 extraídos para emenda {dados['codigo_emenda']}",
            extra={"codigo_emenda": dados["codigo_emenda"], "ano": dados["ano"]},
        )

        return dados

    def montar_params_a2(self, dados_a1: dict, page_size: int = 1000) -> dict:
        """
        Constrói o dicionário de parâmetros para a requisição ao endpoint A2.

        Usa codigo_emenda como chave primária do relacionamento A1→A2.
        Os demais campos são filtros requeridos pela API para retornar os
        documentos corretos da emenda.

        Args:
            dados_a1:  Saída de extrair_dados_a1.
            page_size: Tamanho de página do A2 (padrão 1000 — traz todos os
                       documentos de uma emenda de uma vez).

        Returns:
            Dicionário de parâmetros pronto para urlencode.
        """
        return {
            "paginacaoSimples":   "false",
            "tamanhoPagina":      str(page_size),
            "offset":             "0",
            "direcaoOrdenacao":   "asc",
            "colunaOrdenacao":    "data",
            "colunasSelecionadas": "data,fase,codigoDocumentoResumido,favorecido,valor",
            "codigo":             dados_a1["codigo_emenda"],
            "ano":                dados_a1["ano"],
            "codigoFuncao":       dados_a1["codigo_funcao"],
            "codigoSubfuncao":    dados_a1["codigo_subfuncao"],
            "localidadeDoGasto":  dados_a1["localidade_do_gasto"],
            "skTipoEmenda":       dados_a1["sk_tipo_emenda"],
            "palavraChave":       "",
        }

    def construir_item(self, dados_a1: dict, doc: dict) -> EmendaParlamentarItem:
        """
        Consolida os campos do A1 e de um documento do A2 em um EmendaParlamentarItem.

        Chamado uma vez por documento retornado pelo A2 — a granularidade final
        é um item por documento (OB, NE ou NS) por emenda.

        Args:
            dados_a1: Saída de extrair_dados_a1.
            doc:      Um elemento de data[] do payload A2
                      (/emendas/documentos-relacionados/resultado).

        Returns:
            EmendaParlamentarItem populado com todos os campos A1, A2 e
            metadados de auditoria (data_extracao).
        """
        return EmendaParlamentarItem(
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
            # Metadados de auditoria
            data_extracao=datetime.datetime.utcnow().isoformat(),
        )
