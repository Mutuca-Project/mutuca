import scrapy

class CityHallPublicWorksItem(scrapy.Item):
    numero_licitacao_modalidade = scrapy.Field()
    descricao_projeto = scrapy.Field()  
    convenio = scrapy.Field()  
    contratado = scrapy.Field() 
    contrato = scrapy.Field()  
    aditivo = scrapy.Field()  
    despesas = scrapy.Field()  
    valor_total_pago = scrapy.Field()  
    status = scrapy.Field()  
    fase_projeto = scrapy.Field()  
    percentual_conclusao = scrapy.Field() 
    todos_documentos = scrapy.Field()  
    coordenadas_geograficas = scrapy.Field() 