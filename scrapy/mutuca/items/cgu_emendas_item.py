"""
Item: EmendaParlamentarItem

Representa um documento de execução orçamentária vinculado a uma emenda parlamentar,
consolidando campos dos endpoints A1 (emenda) e A2 (documentos relacionados) da CGU.

Granularidade: um item por documento (OB, NE, NS) por emenda.
A distinção por fase é responsabilidade da camada Silver.
"""

import scrapy


class EmendaParlamentarItem(scrapy.Item):
    # ------------------------------------------------------------------
    # Campos do Endpoint A1 — /emendas/consulta/resultado
    # ------------------------------------------------------------------
    autor = scrapy.Field()
    codigo_emenda = scrapy.Field()
    tipo_emenda = scrapy.Field()
    sk_tipo_emenda = scrapy.Field()
    localidade_do_gasto = scrapy.Field()
    codigo_funcao = scrapy.Field()
    funcao = scrapy.Field()
    codigo_subfuncao = scrapy.Field()
    subfuncao = scrapy.Field()
    programa = scrapy.Field()
    acao = scrapy.Field()
    plano_orcamentario = scrapy.Field()
    numero_emenda = scrapy.Field()
    ano = scrapy.Field()
    # Valores agregados da emenda (totais do A1)
    valor_total_a1 = scrapy.Field()
    valor_empenhado = scrapy.Field()
    valor_liquidado = scrapy.Field()
    valor_resto_inscrito = scrapy.Field()
    valor_resto_cancelado = scrapy.Field()
    valor_resto_pago = scrapy.Field()
    possui_apoio_solicitante = scrapy.Field()

    # ------------------------------------------------------------------
    # Campos do Endpoint A2 — /emendas/documentos-relacionados/resultado
    # ------------------------------------------------------------------
    codigo_documento = scrapy.Field()
    fase_documento = scrapy.Field()   # OB | NE | NS
    data_documento = scrapy.Field()
    favorecido = scrapy.Field()       # CNPJ/Nome do beneficiário final
    valor_documento = scrapy.Field()

    # ------------------------------------------------------------------
    # Metadados de auditoria
    # ------------------------------------------------------------------
    data_extracao = scrapy.Field()    # Timestamp UTC da extração (obrigatório — gate dbt)
