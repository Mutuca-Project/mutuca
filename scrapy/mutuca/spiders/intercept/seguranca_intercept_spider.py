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

        item["url"] = response.url

        manchete_xpath = response.xpath(
            '//div[contains(@class, "single-head")]//h1//text()'
        ).getall()
        manchete = "".join(manchete_xpath).strip() if manchete_xpath else None

        if not manchete:
            manchete_xpath = response.xpath(
                '//section[contains(@class, "single-hero-full")]//h1[contains(@class, "content-excert")]//text()'
            ).getall()
            manchete = "".join(manchete_xpath).strip() if manchete_xpath else None

        if not manchete:
            # Fallback SEO
            manchete = response.xpath('//meta[@property="og:title"]/@content').get()

        item["manchete"] = manchete.strip() if manchete else None

        lide = response.xpath('//meta[@property="og:description"]/@content').get()

        if not lide:
            lide = response.xpath('//meta[@name="description"]/@content').get()

        # Fallback de segurança: Se o SEO falhar, tentamos a raspagem visual do template padrão.
        # O [1] garante que pegaremos apenas o PRIMEIRO parágrafo.
        # A condição not(ancestor::...) garante que ignoraremos o bloco de autores.
        if not lide:
            lide_xpath = response.xpath(
                '(//div[contains(@class, "single-head")]//p[not(ancestor::div[contains(@class, "single-authors-body")])])[1]//text()'
            ).getall()
            lide = "".join(lide_xpath).strip() if lide_xpath else None

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

        item["data_extracao"] = datetime.now(timezone.utc).isoformat()

        yield item
