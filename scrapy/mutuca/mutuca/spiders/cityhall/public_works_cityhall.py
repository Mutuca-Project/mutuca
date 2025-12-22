import logging
import re
from datetime import datetime

from scrapy import Request, Spider

from mutuca.core.public_work_data_collector import PublicWorksDataCollector
from mutuca.items.public_works_cityhall_items import CityHallPublicWorksItem
from mutuca.utils.constants import PUBLIC_WORK_DEFAULT_SELECTORS
from mutuca.utils.logger import get_logger

logger = get_logger(__name__)


class PublicWorksCityHallSpider(Spider):
    """
    Spider responsável pela coleta automatizada de dados de obras públicas
    do Portal da Transparência da Prefeitura de Caruaru (PE).

    Fluxo de execução:
    1. Acessa página inicial do portal da transparência do município de Caruaru.
    2. Navega para seção de obras públicas.
    3. Coleta links de todas as obras da listagem.
    4. Para cada obra, acessa a página de detalhes.
    5. Delea a extração de dados para PublicWorksDataColector
    6. Trata paginação automaticamente

    Arquitetura:
    - Spider: Responsável por navegação e agendamento
    - Collector: Responsável por extração e extruturação
    - XPathCleaner: Responsável por limpeza de caracteres indesejados
    - Logger: Responsável por logging estruturado

    Atributos:
        name (str): Identificador único da spider
        start_urls (list): URLs iniciais para início do scraping
        custom_settings (dict): Configurações específicas da spider
        data_collector (PublicWorksDataColector): Instância do coletor
    """

    name = "public_works_cityhall"
    start_urls = ["https://caruaru.pe.gov.br/portal-da-transparencia/obras-publicas/"]

    custom_settings = {
        "FEEDS": {"public_works_test.json": {"format": "json"}},
        "CONCURRENT_REQUESTS": 8,  # Controle de concorrência
        "DOWNLOAD_DELAY": 0.5,  # Delay entre requisições (boa prática)
    }

    def __init__(self, *args, **kwargs):
        """
        Inicializa a spider e o data collector.

        O collector é instanciado com os seletores padrão definidos
        em `constants.py`.
        """
        super().__init__(*args, **kwargs)

        self.data_collector = PublicWorksDataCollector(
            selectors=PUBLIC_WORK_DEFAULT_SELECTORS
        )

        logger.info(
            "Spider iniciada",
            extra={
                "spider_name": self.name,
                "selectors_loaded": len(PUBLIC_WORK_DEFAULT_SELECTORS),
            },
        )

    # def _clean_xpath_results(self, values):
    #     cleaned_values = []
    #     for item in values:
    #         # Remove tags <div> e </div>
    #         text = re.sub(r"<div[^>]*>", "", item)
    #         text = re.sub(r"</div>", "", text)
    #         # Remove quebras de linha e espaços extras
    #         text = text.replace("\n", "").strip()
    #         # Remove múltiplos espaços internos
    #         text = re.sub(r"\s+", " ", text)
    #         # Adiciona apenas se não for vazio
    #         if text:
    #             cleaned_values.append(text)

    #     return cleaned_values

    # def _concat_keys_and_values(self, keys, values):
    #     return dict(zip(keys, values))

    def parse(self, response, **kwargs):
        """
        Callback inicial: localiza e segue link para obras públicas.

        Este método processa a página de obras públicas do portal da transparência
        e navega para a seção de obras públicas.

        Args:
            response (scrapy.http.Reaponse): Reaponse da página inicial

        Yields:
            scrapy.Request: Requisição para página de listagem de obras
        """

        logger.info(
            "Processando página inicial",
            extra={"url": response.url},
        )

        public_works_urls = response.xpath(
            '//section[@class="groupBox contrast"]/a[contains(@class, "box status")]/@href'
        ).getall()

        for public_work_url in public_works_urls:
            yield Request(public_work_url, callback=self.get_public_work_data)

        next_page = response.xpath(
            '//div[@class="component-pagination"]/a[@class="next page-numbers"]/@href'
        ).get()

        if next_page:
            yield Request(next_page, callback=self.parse)
        else:
            self.logger.info("Não ha mais dados para coletar. Finalizado!")

    def get_public_work_data(self, response):

        logger.info(
            "Iniciando a extreação de dados da obra...", extra={"url": response.url}
        )

        try:
            item = self.data_collector.parse_public_work_data(
                response=response, item_class=CityHallPublicWorksItem
            )

            extraction_summary = item.get("extraction_summary", {})
            logger.info(
                "Extração concluída com sucesso.",
                extra={
                    "url": response.url,
                    "success_rate": extraction_summary.get("success_rate"),
                    "quality": extraction_summary.get("extraction_quality"),
                    "sections_processed": extraction_summary.get(
                        "total_sections_processed"
                    ),
                },
            )

            yield item

        except Exception as e:
            logger.error(
                "Erro crítico na extração dos dados da obra",
                extra={
                    "url": response.url,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    def errback_http(self, failure):
        """
        Callback de erro para requisições HTTP falhas.

        Trata erros de rede, timeouts e outras falhas HTTP,
        registrando informações detalhadas para debugging.

        Args:
            failure (twisted.python.failure.Failure): Objeto de falha do Scrapy
        """

        logger.error(
            "Erro HTTP na requisição",
            extra={
                "url": failure.request.url,
                "error_typy": failure.type.__name__,
                "error_message": str(failure.value),
            },
        )

    def closed(self, reason):
        """
        Callback executado quando a spider é fechada.

        Registra estatísticas finais e motivo do fechamento.

        Args:
            reason (str): Motivo do fechamento da spider
        """

        logger.info(
            f"Spider encerrada: {reason}",
            extra={"spider_name": self.name, "reason": reason},
        )

    # def parse_public_work_data(self, response):

    #     item_data = {}

    #     for section_name, xpaths in PUBLIC_WORK_DEFAULT_SELECTORS.items():
    #         # 1 Extrai a categoria e o valor
    #         categories = [
    #             category.strip()
    #             for category in response.xpath(xpaths["categories"]).getall()
    #         ]
    #         raw_values = response.xpath(xpaths["values"]).getall()

    #         # 2 Limpa os valores obtidos
    #         clean_values = self._clean_xpath_results(raw_values)

    #         # 3 Concatena em um dicionário
    #         item_data[section_name] = self._concat_keys_and_values(
    #             categories, clean_values
    #         )

    #     # 4 Adiciona work_location separadamente (não segue o padrão categorias/valores)
    #     item_data["work_location"] = response.xpath(
    #         '//section[@class="map-obra"]/iframe/@src'
    #     ).get()
    #     item_data["source_url"] = response.url
    #     item_data["extraction_date"] = datetime.now()

    #     # 5 Cria e retorna o Item
    #     item = CityHallPublicWorksItem(**item_data)

    #     yield item
