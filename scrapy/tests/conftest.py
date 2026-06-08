"""
conftest.py — Fixtures compartilhadas entre todos os testes de spiders.

Fornece:
  - fake_response: factory que cria scrapy.http.TextResponse a partir de um
    arquivo JSON de fixture, sem realizar nenhuma chamada HTTP real.
  - spider_cgu: instância pré-configurada de EmendasParlamentaresSpider.
"""

import json
from pathlib import Path

import pytest
import scrapy.http

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(relative_path: str) -> bytes:
    """Lê um arquivo de fixture e retorna o conteúdo como bytes."""
    fixture_path = FIXTURES_DIR / relative_path
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture não encontrada: {fixture_path}")
    return fixture_path.read_bytes()


def fake_response(
    fixture_path: str,
    url: str = "https://portaldatransparencia.gov.br/fake",
    meta: dict | None = None,
    cb_kwargs: dict | None = None,
) -> scrapy.http.TextResponse:
    """
    Cria uma scrapy.http.TextResponse a partir de um arquivo JSON de fixture.

    Args:
        fixture_path: Caminho relativo a tests/fixtures/ (ex: "cgu/a1_response.json").
        url:          URL fictícia associada à resposta.
        meta:         Dicionário de meta do Request (ex: {"offset": 0}).
        cb_kwargs:    Argumentos extras do callback (ex: {"dados_a1": {...}}).

    Returns:
        TextResponse pronta para ser passada diretamente aos callbacks do spider.
    """
    body = _load_fixture(fixture_path)

    request = scrapy.http.Request(
        url=url,
        meta=meta or {},
        cb_kwargs=cb_kwargs or {},
    )

    return scrapy.http.TextResponse(
        url=url,
        body=body,
        encoding="utf-8",
        request=request,
    )


@pytest.fixture
def spider_cgu():
    """
    Instância de EmendasParlamentaresSpider configurada para testes.

    Usa de=2026, ate=2026 por padrão. Override via parâmetros diretos se necessário.
    O custom_settings.FEEDS é sobrescrito para evitar gravação de arquivo durante testes.
    """
    from mutuca.spiders.cgu.emendas_parlamentares import EmendasParlamentaresSpider

    spider = EmendasParlamentaresSpider.__new__(EmendasParlamentaresSpider)
    EmendasParlamentaresSpider.__init__(spider, de="2026", ate="2026")
    spider.custom_settings = {}  # desativa FEEDS — sem arquivo de saída nos testes
    return spider
