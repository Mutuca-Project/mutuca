from scrapy import Spider

class PublicWorksCityHallSpyder(Spider):
    name = "public_works_cityhall"
    start_urls = ["https://caruaru.pe.gov.br/portal-da-transparencia/obras-publicas/"]

    def parse(self, response, **kargs):
        pass

