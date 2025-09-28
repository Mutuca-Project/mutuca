import scrapy


class CityHallPublicWorksItem(scrapy.Item):
    general_info = scrapy.Field()
    contract = scrapy.Field()
    contracted = scrapy.Field()
    fiscal_year_expenditures = scrapy.Field()
    contract_amendment = scrapy.Field()
    cumulative_amount_paid = scrapy.Field()
    all_documents = scrapy.Field()
    work_location = scrapy.Field()

