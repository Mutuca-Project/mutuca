import scrapy


class CityHallPublicWorksItem(scrapy.Item):
    modality_bidding_number = scrapy.Field()
    project_description = scrapy.Field()
    agreement = scrapy.Field()
    contracted = scrapy.Field()
    contract = scrapy.Field()
    amendment = scrapy.Field()
    expenses = scrapy.Field()
    total_paid_amount = scrapy.Field()
    status = scrapy.Field()
    project_stage = scrapy.Field()
    completion_percentage = scrapy.Field()
    all_documents = scrapy.Field()
    geo_coordinates = scrapy.Field()

