import scrapy

from mutuca.items import ParliamentaryAllowanceItem
from mutuca.spiders import BaseCaruaruParliamentaryAllowanceSpider


class ParliamentaryMealAllowanceSpider(BaseCaruaruParliamentaryAllowanceSpider):
    name = "parliamentary_meal_allowance"
    custom_settings = {
        "FEEDS": {
            "parliamentary_allowance_metadata.json": {
                "format": "json",
                "overwrite": False,
            }
        }
    }

    def start_requests(self):
        url = f"https://transparenciape.com.br/CamaraCaruaru/cotaAtividadeParlamentarClass.php?dataInicial={self.start_date}&dataFinal={self.end_date}&rowCount={self.row_count}"

        yield scrapy.Request(url)

    def parse(self, response):
        url_base = "http://transparencia.caruaru.pe.leg.br/sistema/uploads/cotas/"

        for row in response.json()["rows"]:
            if "Alimentação" in row["descricao"]:
                url = url_base + row["arquivo"]
                publication_date = row["data_publicacao"]
                description = row["descricao"]
                file_id = row["arquivo"]

                yield ParliamentaryAllowanceItem(
                    file_urls=[url],
                    url=url,
                    publication_date=publication_date,
                    description=description,
                    file_id=file_id,
                )
