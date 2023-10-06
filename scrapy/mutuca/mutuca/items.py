# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy


class ParliamentaryAllowanceItem(scrapy.Item):
    file_urls = scrapy.Field()
    files = scrapy.Field()
    url = scrapy.Field()
    publication_date = scrapy.Field()
    description = scrapy.Field()
    category = scrapy.Field()
    file_id = scrapy.Field()
