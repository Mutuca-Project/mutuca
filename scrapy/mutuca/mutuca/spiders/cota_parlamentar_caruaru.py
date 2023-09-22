import scrapy
from mutuca.items import MutucaItem


class CotaParlamentarCaruaruSpider(scrapy.Spider):
    name = "cota_parlamentar"

    custom_settings = {
        "FEEDS": {
            "datatest.json": {"format": "json", "ovewrite": True}
        }
    }

    def start_requests(self):
        # definir a data com o módulo date para a data do momento da raspagem
        start_date = "01/01/2000"
        end_date = "18/09/2023"
        row_count = "-1"
        url = f"https://transparenciape.com.br/CamaraCaruaru/cotaAtividadeParlamentarClass.php?dataInicial={start_date}&dataFinal={end_date}&rowCount={row_count}"

        yield scrapy.Request(url)

    def parse(self, response):
        rows = response.json()["rows"]
        url_base = "http://transparencia.caruaru.pe.leg.br/sistema/uploads/cotas/"

        for row in rows:
            url = url_base + row["arquivo"]
            mutuca_item = MutucaItem()
            mutuca_item["url"] = url
            mutuca_item["publication_date"] = row["data_publicacao"]
            mutuca_item["description"] = row["descricao"]
            mutuca_item["file_id"] = row["arquivo"]

            yield mutuca_item
