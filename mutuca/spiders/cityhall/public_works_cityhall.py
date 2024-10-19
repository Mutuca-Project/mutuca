import re
from logging import info

from scrapy import Request, Spider

from mutuca.items.public_works_cityhall_items import CityHallPublicWorksItem


class PublicWorksCityHallSpyder(Spider):
    name = "public_works_cityhall"
    start_urls = ["https://caruaru.pe.gov.br/portal-da-transparencia/"]

    def parse(self, response, **kargs):
        public_works_url = response.xpath(
            '//div[@class="component_pt-cardItemBig contrast title-acesso-a-informacao"]/a[contains(@href, "obras-publicas")]/@href'
        ).get()

        yield Request(public_works_url, callback=self.parse_public_works_cards)

    def parse_public_works_cards(self, response, **kargs):

        public_works_cards = response.xpath(
            '//section[@class="groupBox contrast"]/a[contains(@class, "box status")]/@href'
        ).getall()

        for public_work_url in public_works_cards:
            yield Request(public_work_url, callback=self.parse_public_work_data)

        pagination = response.xpath(
            '//div[@class="component-pagination"]/a[@class="next page-numbers"]/@href'
        ).get()

        if pagination:
            yield Request(pagination, callback=self.parse_public_works_cards)
        else:
            info("Não ha mais páginas para raspar.")

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

        item["numero_licitacao_modalidade"] = (
            formatted_values[0].strip() if len(formatted_values) > 0 else None
        )
        item["descricao_projeto"] = (
            formatted_values[1].strip() if len(formatted_values) > 1 else None
        )

        item["convenio"] = {
            nested_keys[0].strip(): formatted_values[2].strip(),
            nested_keys[1].strip(): formatted_values[3].strip(),
        }
        item["contratado"] = {
            nested_keys[2].strip(): formatted_values[4].strip(),
            nested_keys[3].strip(): formatted_values[5].strip(),
        }
        item["contrato"] = {
            nested_keys[4].strip(): formatted_values[6].strip(),
            nested_keys[5].strip(): formatted_values[7].strip(),
            nested_keys[6].strip(): formatted_values[8].strip(),
            nested_keys[7].strip(): formatted_values[9].strip(),
            nested_keys[8].strip(): formatted_values[10].strip(),
        }
        item["aditivo"] = {
            nested_keys[9].strip(): formatted_values[11].strip(),
            nested_keys[10].strip(): formatted_values[12].strip(),
        }
        item["despesas"] = {
            nested_keys[11].strip(): formatted_values[13].strip(),
            nested_keys[12].strip(): formatted_values[14].strip(),
            nested_keys[13].strip(): formatted_values[15].strip(),
        }
        item["valor_total_pago"] = (
            formatted_values[16].strip() if len(formatted_values) > 16 else None
        )
        item["status"] = (
            formatted_values[17].strip() if len(formatted_values) > 17 else None
        )
        item["fase_projeto"] = (
            formatted_values[18].strip() if len(formatted_values) > 18 else None
        )
        item["percentual_conclusao"] = (
            formatted_values[19].strip() if len(formatted_values) > 19 else None
        )

        item["todos_documentos"] = (
            dict(zip(documents_title, documents_urls))
            if documents_title and documents_urls
            else None
        )

        item["coordenadas_geograficas"] = coordinate_source

        yield item
