from datetime import datetime, timezone

import scrapy
from mutuca.items.intercept_items import InterceptArticleItem


class InterceptSegurancaSpider(scrapy.Spider):
    name = "intercept_seguranca"
    allowed_domains = ["intercept.com.br"]
    start_urls = ["https://www.intercept.com.br/seguranca/"]

    current_page = 1

    def parse(self, response):
        self.logger.info(f"Raspando página de índice: {response.url}")

        # Extrai todos os links das matérias na página atual
        article_links = response.xpath(
            '//div[contains(@class, "archive-list-feed")]//article/a/@href'
        ).getall()

        for link in article_links:
            yield response.follow(link, callback=self.parse_article)

        if article_links:
            self.current_page += 1
            next_page_url = (
                f"https://www.intercept.com.br/seguranca/page/{self.current_page}/"
            )
            yield scrapy.Request(url=next_page_url, callback=self.parse)

    def parse_article(self, response):
        self.logger.info(f"Extraindo matéria: {response.url}")

        item = InterceptArticleItem()

        manchete = response.xpath(
            '//div[contains(@class, "single-head")]//h1/text()'
        ).get()
        item["manchete"] = manchete.strip() if manchete else None

        lide = response.xpath('//div[contains(@class, "single-head")]//p/text()').get()
        item["lide"] = lide.strip() if lide else None

        autores = '//div[contains(@class, "single-authors-body")]/p/a/@title'
        item["autores"] = response.xpath(autores).getall()

        item["data_publicacao"] = response.xpath(
            '//div[contains(@class, "single-authors-body")]/time/@datetime'
        ).get()

        text_nodes = response.xpath(
            '//div[contains(@class, "single-content")]/*[self::p or self::h2 or self::h3 or self::blockquote]//text()'
        ).getall()

        text_clean_list = [text.strip() for text in text_nodes if text.strip()]

        # Agrupa o texto completo
        item["corpo_materia"] = " ".join(text_clean_list)

        item["data_publicacao"] = datetime.now(timezone.utc).isoformat()

        yield item
