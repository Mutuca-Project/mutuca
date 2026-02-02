import scrapy
from scrapy.http import HtmlResponse


class TestSpider(scrapy.Spider):
    name = "teste_ingestao"
    start_urls = ["http://quotes.toscrape.com/"]

    def parse(self, response):

        self.logger.info(f"Analizando url: {response.url}")
        self.logger.info(f"Tipo da resposta: {type(response)}")

        if not isinstance(response, HtmlResponse):
            self.logger.warning(
                f"Ignorando URL não texto: {response.url} (Content-Type: {response.heders.get('Content-Type')})"
            )

        # Extrai frases e autores
        for quote in response.css("div.quote"):
            yield {
                "texto": quote.css("span.text::text").get(),
                "autor": quote.css("small.author::text").get(),
                "tags": quote.css("div.tags a.tag::text").getall(),
                "url_origem": response.url,
            }

        # Paginação (raspa apenas 2 páginas para teste)
        next_page = response.css("li.next a::attr(href)").get()
        if next_page and "/page/3/" not in next_page:
            yield response.follow(next_page, self.parse)
