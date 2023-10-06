import scrapy

from mutuca.items import ParliamentaryAllowanceItem
from mutuca.spiders import BaseCaruaruParliamentaryAllowanceSpider


class ParliamentaryMealAllowanceSpider(BaseCaruaruParliamentaryAllowanceSpider):
    name = "cota_parlamentar"
    # start_date = "01/01/2000"
    # end_date = datetime.now().strftime("%d/%m/%Y")
    # row_count = "-1"
    custom_settings = {"FEEDS": {"datatest.json": {"format": "json", "ovewrite": True}}}

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
                    category="ALIMENTAÇÃO",
                    file_id=file_id,
                )
