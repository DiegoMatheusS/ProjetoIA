from src.technical_ai.providers import OpenAIProvider


def test_openai_request_asks_for_web_search_sources(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_WEB_SEARCH", "true")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5.6-luna")

    provider = OpenAIProvider()
    body = provider._request_body("pesquise a ficha tecnica")

    assert body["model"] == "gpt-5.6-luna"
    assert body["tools"] == [{"type": "web_search"}]
    assert body["include"] == ["web_search_call.action.sources"]


def test_openai_sources_reads_web_search_call_and_annotations_without_duplicates():
    data = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {
                            "url": "https://www.msi.com/Motherboard/B550-A-PRO/Specification",
                            "title": "MSI B550-A PRO Specification",
                        },
                        {
                            "url": "https://www.techpowerup.com/gpu-specs/example",
                            "title": "TechPowerUp",
                        },
                    ]
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "chipset: B550",
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://www.msi.com/Motherboard/B550-A-PRO/Specification",
                                "title": "MSI B550-A PRO Specification",
                            },
                            {
                                "type": "url_citation",
                                "url": "https://example.com/manual",
                                "title": "Manual",
                            },
                        ],
                    }
                ],
            },
        ]
    }

    sources = OpenAIProvider._sources(data)

    assert [item["url"] for item in sources] == [
        "https://www.msi.com/Motherboard/B550-A-PRO/Specification",
        "https://www.techpowerup.com/gpu-specs/example",
        "https://example.com/manual",
    ]
    assert sources[0]["titulo"] == "MSI B550-A PRO Specification"
