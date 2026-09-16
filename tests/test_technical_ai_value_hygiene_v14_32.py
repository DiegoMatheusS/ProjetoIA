from src.extractors.meta_ai_whatsapp import (
    build_meta_ai_prompt,
    merge_meta_ai_response_into_payload_detailed,
    parse_meta_ai_response,
)


def _motherboard_payload():
    return {
        "categoria": "PLACA_MAE",
        "nome": "ASRock B650E PG Riptide WIFI",
        "marca": "ASRock",
        "modelo": "B650E PG Riptide WIFI",
        "especificacaoPlacaMae": {
            "socket": "AM5",
            "chipset": "B650E",
            "formato": "ATX",
            "slotsMemoria": 4,
            "wifi": True,
        },
    }


def test_web_search_markdown_citations_do_not_pollute_technical_values():
    text = (
        "biosInicial: 1.11 ([asrock.com](https://www.asrock.com/support/cpu.asp?s=AM5&u=703))\n"
        "saidasVideo: 1 x HDMI 2.1 ([pg.asrock.com](https://pg.asrock.com/mb/AMD/B650E%20PG%20RIPTIDE%20WIFI/index.asp))\n"
        "ethernet: Killer E3100G, 2,5 Gigabit ([pg.asrock.com](https://pg.asrock.com/mb/AMD/B650E%20PG%20RIPTIDE%20WIFI/index.asp))"
    )

    specs = parse_meta_ai_response("PLACA_MAE", text)

    assert specs["biosInicial"] == "1.11"
    assert specs["saidasVideo"] == ["1 x HDMI 2.1"]
    assert specs["ethernet"] == "Killer E3100G, 2,5 Gigabit"
    assert "http" not in repr(specs).lower()
    assert "asrock.com" not in repr(specs).lower()


def test_clean_values_are_written_to_payload_instead_of_citations():
    text = (
        "biosInicial: 1.11 ([asrock.com](https://www.asrock.com/support/cpu.asp?s=AM5&u=703))\n"
        "ethernet: Killer E3100G, 2,5 Gigabit ([pg.asrock.com](https://pg.asrock.com/mb/AMD/B650E%20PG%20RIPTIDE%20WIFI/index.asp))"
    )

    payload, filled, interpreted, conflicts = merge_meta_ai_response_into_payload_detailed(
        "PLACA_MAE",
        _motherboard_payload(),
        text,
    )

    specs = payload["especificacaoPlacaMae"]
    assert specs["biosInicial"] == "1.11"
    assert specs["ethernet"] == "Killer E3100G, 2,5 Gigabit"
    assert set(filled) == {"biosInicial", "ethernet"}
    assert interpreted["biosInicial"] == "1.11"
    assert conflicts == []


def test_structured_json_values_are_sanitized_too():
    text = '''{
      "biosInicial": "1.11 ([asrock.com](https://www.asrock.com/support/cpu.asp?s=AM5&u=703))",
      "ethernet": "Killer E3100G 2.5GbE (https://pg.asrock.com/spec)"
    }'''

    specs = parse_meta_ai_response("PLACA_MAE", text)

    assert specs["biosInicial"] == "1.11"
    assert specs["ethernet"] == "Killer E3100G 2.5GbE"


def test_prompt_explicitly_forbids_sources_inside_field_values():
    prompt = build_meta_ai_prompt(
        "PLACA_MAE",
        "ASRock B650E PG Riptide WIFI",
        ["biosInicial", "ethernet"],
    )

    assert "SOMENTE o dado técnico" in prompt
    assert "Não inclua URL" in prompt
    assert "fontes são coletadas separadamente" in prompt
