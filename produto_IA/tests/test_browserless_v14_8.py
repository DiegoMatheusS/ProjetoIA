import os
from unittest.mock import patch

from src.scrapers.browser_scraper import BrowserScraper


def test_browserless_missing_token_is_explicit():
    with patch.dict(os.environ, {}, clear=True):
        r = BrowserScraper().fetch_browserless("https://example.com")
    assert r["error"] == "BROWSERLESS_NAO_CONFIGURADO"
    assert r["browserless"] is True


def test_browserless_configured_from_env():
    with patch.dict(os.environ, {"BROWSERLESS_TOKEN": "abc", "BROWSERLESS_PROXY": "residential", "BROWSERLESS_PROXY_COUNTRY": "BR"}, clear=True):
        assert BrowserScraper().browserless_configured() is True
