import logging
import re
from datetime import datetime

from scrapy import Request, Spider

from mutuca.items.public_works_cityhall_items import CityHallPublicWorksItem
from mutuca.utils.constants import PUBLIC_WORK_DEFAULT_SELECTORS


class PublicWorksCityHallSpider(Spider):
    """
    Spider responsável por coletar dados sobre obras públicas disponibilizadas
    no Portal da Transparência da Prefeitura de Caruaru (PE).

    Esta spider percorre a listagem de obras públicas e extrai informações detalhadas
    de cada projeto, incluindo dados contratuais, status de execução, despesas,
    documentos relacionados e coordenadas geográficas.

    Dados extraídos:
        - Número e modalidade da licitação
        - Descrição do projeto
        - Informações sobre convênio e contratado
        - Detalhes do contrato e aditivos
        - Despesas e valores pagos
        - Status da obra, fase do projeto e percentual de conclusão
        - Lista de documentos anexos (título + URL)
        - Coordenadas geográficas (iframe do mapa)

    Os dados são organizados no item CityHallPublicWorksItem e enviados para
    o pipeline de upload em JSON no armazenamento OCI (Oracle Cloud Infrastructure).

    A spider também trata a paginação automaticamente até o fim da listagem de obras.

    Atributos:
        name (str): Nome da spider.
        start_urls (list): Lista com a URL inicial do Portal da Transparência.
        custom_settings (dict): Configuração do pipeline utilizado.

    Métodos:
        parse(response):
            Localiza e segue o link para a seção de obras públicas.

        parse_public_works_cards(response):
            Coleta os links de todas as obras públicas exibidas na página e
            agenda requisições para suas respectivas páginas de detalhes.
            Também lida com a paginação da listagem.

        parse_public_work_data(response):
            Extrai e estrutura os dados de uma obra pública individual.

    """

    # logger = Logger(__name__)

    name = "public_works_cityhall"
    start_urls = ["https://caruaru.pe.gov.br/portal-da-transparencia/obras-publicas/"]

    custom_settings = {
        "FEEDS": {"public_works_test.json": {"format": "json"}},
    }

    def _clean_xpath_results(self, values):
        cleaned_values = []
        for item in values:
            # Remove tags <div> e </div>
            text = re.sub(r"<div[^>]*>", "", item)
            text = re.sub(r"</div>", "", text)
            # Remove quebras de linha e espaços extras
            text = text.replace("\n", "").strip()
            # Remove múltiplos espaços internos
            text = re.sub(r"\s+", " ", text)
            # Adiciona apenas se não for vazio
            if text:
                cleaned_values.append(text)

        return cleaned_values

    def _concat_keys_and_values(self, keys, values):
        return dict(zip(keys, values))

    def parse(self, response, **kargs):
        public_works_urls = response.xpath(
            '//section[@class="groupBox contrast"]/a[contains(@class, "box status")]/@href'
        ).getall()

        for public_work_url in public_works_urls:
            yield Request(public_work_url, callback=self.parse_public_work_data)

        next_page = response.xpath(
            '//div[@class="component-pagination"]/a[@class="next page-numbers"]/@href'
        ).get()

        if next_page:
            yield Request(next_page, callback=self.parse)
        else:
            self.logger.info("Não ha mais dados para coletar. Finalizado!")

    def parse_public_work_data(self, response):

        item_data = {}

        for section_name, xpaths in PUBLIC_WORK_DEFAULT_SELECTORS.items():
            # 1 Extrai a categoria e o valor
            categories = [
                category.strip()
                for category in response.xpath(xpaths["categories"]).getall()
            ]
            raw_values = response.xpath(xpaths["values"]).getall()

            # 2 Limpa os valores obtidos
            clean_values = self._clean_xpath_results(raw_values)

            # 3 Concatena em um dicionário
            item_data[section_name] = self._concat_keys_and_values(
                categories, clean_values
            )

        # 4 Adiciona work_location separadamente (não segue o padrão categorias/valores)
        item_data["work_location"] = response.xpath(
            '//section[@class="map-obra"]/iframe/@src'
        ).get()
        item_data["source_url"] = response.url
        item_data["extraction_date"] = datetime.now()

        # 5 Cria e retorna o Item
        item = CityHallPublicWorksItem(**item_data)

        yield item
