import os
from os.path import join
from typing import Any

from dotenv import load_dotenv
from lxml.html import urljoin

from scrapy import Request, Spider
from scrapy.http import Response

load_dotenv()


class ReceitaFederalCnpjSpider(Spider):
    name = "dados_abertos_receita_federal_cnpj"
    start_urls = ["https://dados-abertos-rf-cnpj.casadosdados.com.br/arquivos/"]
    # allowed_domains = []
    custom_settings = {
        "ITEM_PIPELINES": {
            "mutuca.pipelines.receita_federal_cnpj_pipeline.ReceitaFederalLocalZipExtractorPipeline": 100,
        },
        "CONCURRENT_REQUESTS": 2,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def parse(self, response: Response, **kwargs: Any) -> Any:

        date_directories = response.xpath(
            "//td/a[starts-with(@href, '2023')]/@href"
        ).getall()

        for date_directory in date_directories:
            directory_url = response.urljoin(date_directory)
            yield Request(url=directory_url, callback=self.parse_directory_files)

    def parse_directory_files(self, response: Response, **kwargs: Any) -> Any:

        date_batch = response.url.strip("/").split("/")[-1]

        # Este projeto, a princípio, utiliza um HD externo para armazenamento do dados
        # TODO: passar a lógica de armazenamento para Airflow no futuro.
        target_dir = os.path.join(os.getenv("SPIDER_RFB_CNPJ_TARGET_DIR", date_batch))

        xpaths = [
            "//td/a[starts-with(@href, 'Empresas')]/@href",
            "//td/a[starts-with(@href, 'Estabelecimentos')]/@href",
            "//td/a[starts-with(@href, 'Socios')]/@href",
        ]

        target_files = []
        for xp in xpaths:
            target_files.extend(response.xpath(xp).getall())

        self.logger.info(
            f"Encontrados {len(target_files)} arquivos de interesse no lote {date_batch}."
        )

        for file in target_files:
            file_url = response.urljoin(file)
            yield {
                "file_url": file_url,
                "file_name": file,
                "target_dir": target_dir,
            }
