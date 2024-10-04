import re

from scrapy import Request, Spider

from mutuca.items.public_works_cityhall_items import CityHallPublicWorksItem


class PublicWorksCityHallSpyder(Spider):
    name = "public_works_cityhall"
    start_urls = ["https://caruaru.pe.gov.br/portal-da-transparencia/obras-publicas/"]

    def parse(self, response, **kargs):
        public_works_urls = response.xpath(
            '//section[@class="groupBox contrast"]/a[contains(@class, "box status")]/@href'
        ).getall()

        for public_work_url in public_works_urls:
            yield Request(public_work_url, callback=self.parse_public_work_data)

    def parse_public_work_data(self, response):
        nested_keys = response.xpath(
            '//div[@class="row-cards"]/div[@class="row-card"]/div[@class="card-title"]/text()'
        ).getall()

        retrive_values = response.xpath(
            '//section[@class="description-obra"]/div[@class="row-details"]//div[@class="card-info"]/text()[normalize-space()]'
        ).getall()

        documents_title = response.xpath(
            '//div[@class="card-info card-info--docs"]/div[@class="attachment"]//p[@class="cardTitle"]/text()'
        ).getall()

        documents_urls = response.xpath(
            '//div[@class="card-info card-info--docs"]/div[@class="attachment"]//div[@class="button"]/a/@href'
        ).getall()

        coordinate_source = response.xpath(
            '//section[@class="map-obra"]//iframe/@src'
        ).getall()

        formatted_values = [re.sub(r"\s+", " ", value) for value in retrive_values]

        item = CityHallPublicWorksItem()

        item["modality_bidding_number"] = (
            formatted_values[0].strip() if len(formatted_values) > 0 else None
        )
        item["project_description"] = (
            formatted_values[1].strip() if len(formatted_values) > 1 else None
        )

        item["agreement"] = {
            nested_keys[0].strip(): formatted_values[2].strip(),
            nested_keys[1].strip(): formatted_values[3].strip(),
        }
        item["contracted"] = {
            nested_keys[2].strip(): formatted_values[4].strip(),
            nested_keys[3].strip(): formatted_values[5].strip(),
        }
        item["contract"] = {
            nested_keys[4].strip(): formatted_values[6].strip(),
            nested_keys[5].strip(): formatted_values[7].strip(),
            nested_keys[6].strip(): formatted_values[8].strip(),
            nested_keys[7].strip(): formatted_values[9].strip(),
            nested_keys[8].strip(): formatted_values[10].strip(),
        }
        item["amendment"] = {
            nested_keys[9].strip(): formatted_values[11].strip(),
            nested_keys[10].strip(): formatted_values[12].strip(),
        }
        item["expenses"] = {
            nested_keys[11].strip(): formatted_values[13].strip(),
            nested_keys[12].strip(): formatted_values[14].strip(),
            nested_keys[13].strip(): formatted_values[15].strip(),
        }
        item["total_paid_amount"] = (
            formatted_values[16].strip() if len(formatted_values) > 16 else None
        )
        item["status"] = formatted_values[17].strip() if len(formatted_values) > 17 else None
        item["project_stage"] = (
            formatted_values[18].strip() if len(formatted_values) > 18 else None
        )
        item["completion_percentage"] = (
            formatted_values[19].strip() if len(formatted_values) > 19 else None
        )

        item["all_documents"] = (
            dict(zip(documents_title, documents_urls))
            if documents_title and documents_urls
            else None
        )

        item["geo_coordinates"] = coordinate_source

        yield item
