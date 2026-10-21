from src.extractors.research_specs import extract_research_specs


def _attr(name, value):
    return {"id": None, "name": name, "value_name": value}


def test_geizhals_motherboard_structured_data_fills_real_fields_without_subcounting():
    attributes = [
        _attr("RAM", "4x DDR5 DIMM-Slots, Dual Channel, max. 256GB UDIMM Non-ECC+ECC"),
        _attr("RAM-Datenrate", "DDR5-5200 (Ryzen 7000/Ryzen 8000G), DDR5-5600 (Ryzen 9000), max. DDR5-7600 OC"),
        _attr("ECC-Unterstützung", "ja"),
        _attr("Anschlüsse extern", "1x HDMI 2.1 (iGPU), 1x USB-C 3.1, 1x RJ-45 (2.5GBase-T, Intel Killer E3100G)"),
        _attr("M.2-Slots", "1x M.2/M-Key (PCIe 5.0 x4, 2280), 1x M.2/M-Key (PCIe 4.0 x4, 2280/2260), 1x M.2/M-Key (PCIe 3.0 x2/SATA, 2280/2260/2242), 1x M.2/E-Key (2230, belegt mit WiFi+BT-Modul)"),
        _attr("Sonstige Schnittstellen", "2x SATA 6Gb/s (B650E), 2x SATA 6Gb/s (ASMedia ASM1061)"),
        _attr("Netzwerk", "Intel Killer E3100G (2.5Gb/s)"),
        _attr("Buttons/Switches", "USB BIOS Flashback (extern)"),
        _attr("Wireless", "Wi-Fi 6E, Bluetooth 5.3"),
    ]

    specs = extract_research_specs("PLACA_MAE", attributes, context_text="ASRock B650E PG Riptide WIFI")

    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["formatosMemoriaSuportados"] == ["DIMM"]
    assert specs["capacidadeMaximaMemoriaGb"] == 256
    assert specs["frequenciasMemoriaJedecMhz"] == [5200, 5600]
    assert specs["frequenciasMemoriaOverclockMhz"] == [7600]
    assert specs["suportaMemoriaRegistrada"] is False
    assert specs["suportaEcc"] is True
    assert specs["portasSata"] == 4
    assert specs["slotsM2"] == 3
    assert specs["ethernet"] == "Intel Killer E3100G (2.5Gb/s)"
    assert specs["saidasVideo"] == ["1 x HDMI 2.1"]
    assert specs["biosFlashback"] is True
    assert specs["wifi"] is True
    assert specs["bluetooth"] is True
