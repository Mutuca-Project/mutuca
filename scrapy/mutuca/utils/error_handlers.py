"""
Utilitários de tratamento de erros para spiders Scrapy.

Uso:
    from mutuca.utils.error_handlers import handle_request_error

    yield scrapy.Request(
        url=url,
        callback=self.parse,
        errback=lambda f: handle_request_error(f, self.log),
    )
"""

from twisted.python.failure import Failure


def handle_request_error(failure: Failure, logger) -> None:
    """
    Loga erros de requisição HTTP de forma estruturada.

    Cobre os casos mais comuns de falha em spiders:
      - HttpError  → status code inesperado (4xx, 5xx)
      - DNSLookupError → host inacessível
      - TimeoutError / TCPTimedOutError → timeout de rede
      - Qualquer outro erro Twisted

    Args:
        failure: Objeto Failure do Twisted, recebido pelo errback do scrapy.Request.
        logger:  Logger do spider (self.log quando usando get_logger de utils/logger.py,
                 ou self.logger para o logger padrão do Scrapy).
    """
    from scrapy.spidermiddlewares.httperror import HttpError
    from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError

    url = getattr(failure.request, "url", "URL desconhecida")

    if failure.check(HttpError):
        response = failure.value.response
        logger.error(
            f"HttpError [{response.status}] ao acessar: {url}",
            extra={"url": url, "status": response.status},
        )
    elif failure.check(DNSLookupError):
        logger.error(
            f"DNSLookupError — host inacessível: {url}",
            extra={"url": url, "erro": "DNSLookupError"},
        )
    elif failure.check(TimeoutError, TCPTimedOutError):
        logger.error(
            f"Timeout na requisição: {url}",
            extra={"url": url, "erro": "TimeoutError"},
        )
    else:
        logger.error(
            f"Erro inesperado na requisição: {url} | {repr(failure.value)}",
            extra={"url": url, "erro": repr(failure.value)},
        )
