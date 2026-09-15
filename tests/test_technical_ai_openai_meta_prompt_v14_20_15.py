from src.technical_ai.providers import TechnicalAIResponse
from src.technical_ai.service import build_technical_ai_prompt, enrich_hardware_with_external_ai


class FakeOpenAI:
    name = "OPENAI"
    configured = True

    def __init__(self, text: str):
        self.text = text
        self.prompts = []

    def enrich(self, prompt: str):
        self.prompts.append(prompt)
        return TechnicalAIResponse(
            provider="OPENAI",
            model="gpt-test",
            text=self.text,
            sources=[{"url": "https://example.com/spec", "titulo": "Ficha"}],
        )


def test_openai_receives_exact_meta_ai_prompt_and_direct_lines_are_applied(monkeypatch):
    payload = {
        "categoria": "PROCESSADOR",
        "nome": "AMD Ryzen 9 7900",
        "marca": "AMD",
        "modelo": "Ryzen 9 7900",
        "especificacaoProcessador": {
            "socket": "AM5",
            "nucleos": 12,
            "threads": 24,
            "tiposMemoriaSuportados": [],
        },
    }
    fake = FakeOpenAI(
        "arquitetura: Zen 4\n"
        "tiposMemoriaSuportados: DDR5\n"
        "socket: AM4"
    )

    monkeypatch.setattr(
        "src.technical_ai.service._local_enrich",
        lambda _category, current: (
            dict(current),
            {"camposPreenchidos": [], "fontesConsultadas": [], "conflitos": []},
        ),
    )
    monkeypatch.setattr(
        "src.technical_ai.service.get_technical_ai_provider",
        lambda _name: fake,
    )
    monkeypatch.setattr(
        "src.technical_ai.service.collect_cited_sources",
        lambda *_args, **_kwargs: None,
    )

    expected_prompt, _missing = build_technical_ai_prompt(
        "PROCESSADOR", "AMD Ryzen 9 7900", payload
    )
    out = enrich_hardware_with_external_ai(
        provider_name="OPENAI",
        category="PROCESSADOR",
        name="AMD Ryzen 9 7900",
        payload=payload,
    )

    assert fake.prompts == [expected_prompt]
    assert "Responda exatamente no formato Campo: valor" in fake.prompts[0]
    assert "formato final é JSON" not in fake.prompts[0]

    specs = out["payload"]["especificacaoProcessador"]
    assert specs["socket"] == "AM5"
    assert specs["arquitetura"] == "Zen 4"
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert "arquitetura" in out["camposPreenchidos"]
    assert "tiposMemoriaSuportados" in out["camposPreenchidos"]
    assert "socket" not in out["camposPreenchidos"]
    assert any(item["campo"] == "socket" for item in out["conflitos"])
    assert out["fontesDeclaradas"] == [
        {"url": "https://example.com/spec", "titulo": "Ficha"}
    ]
