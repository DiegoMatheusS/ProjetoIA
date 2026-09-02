from src.enrichment.search import WebSearchResolver


def test_v14_16_search_resolver_can_return_multiple_deduped_results():
    html = """
      <a class="result__a" href="https://www.cpu-world.com/CPUs/Core_i5/Intel-Core%20i5-9500.html">Intel Core i5-9500</a>
      <a class="result__a" href="https://www.cpu-world.com/CPUs/Core_i5/Intel-Core%20i5-9600.html">Intel Core i5-9600</a>
      <a class="result__a" href="https://www.cpu-world.com/CPUs/Core_i5/Intel-Core%20i5-9500.html">Duplicado</a>
      <a class="result__a" href="https://example.com/outro">Fora</a>
    """
    resolver = WebSearchResolver()
    items = resolver._candidates_from_html(html, ["cpu-world.com"], limit=10)
    assert len(items) == 2
    assert items[0]["title"] == "Intel Core i5-9500"
    assert "i5-9600" in items[1]["url"]
