import scrapy


class InterceptArticleItem(scrapy.Item):
    url = scrapy.Field()
    manchete = scrapy.Field()
    lide = scrapy.Field()
    autores = scrapy.Field()
    data_publicacao = scrapy.Field()
    corpo_materia = scrapy.Field()
    data_extracao = scrapy.Field()
