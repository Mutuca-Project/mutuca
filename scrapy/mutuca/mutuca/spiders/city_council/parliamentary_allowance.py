from datetime import datetime

import scrapy

from mutuca.items.parliamentary_allowance_Items import ParliamentaryAllowanceItem
from mutuca.pipelines.pipeline_builder import PipelineBuilder


class ParliamentaryAllowanceSpider(scrapy.Spider):
    name = "parliamentary_allowance"

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super(ParliamentaryAllowanceSpider, cls).from_crawler(
            crawler, *args, **kwargs
        )

        # Obtém a configuração de pipeline através do builder
        builder = PipelineBuilder()
        pipelines = builder.get_pipelines(spider.name)

        # Aplica as configurações especificas de pipelines
        crawler.settings.set("ITEM_PIPELINES", pipelines)

        return spider

    def start_requests(self):
        start_date = "01/01/2000"
        end_date = datetime.now().strftime("%d/%m/%Y")
        row_count = "-1"
        url = f"https://transparenciape.com.br/CamaraCaruaru/cotaAtividadeParlamentarClass.php?dataInicial={start_date}&dataFinal={end_date}&rowCount={row_count}"

        yield scrapy.Request(url)

    def parse(self, response, **kwargs):
        url_base = "http://transparencia.caruaru.pe.leg.br/sistema/uploads/cotas/"

        for row in response.json()["rows"]:
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
