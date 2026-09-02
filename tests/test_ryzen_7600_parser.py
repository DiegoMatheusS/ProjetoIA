from src.extractors.ml_specs import extract_specs


DESCRIPTION = """Processador Ryzen 5 7600 AM5 3.8GHz 6 Cores 12 Threads Wraith Stealth - 100-100001015BOX - Marca: AMD - Modelo: 100-100001015BOX Especificações Processador AM5 Ryzen 5 7600 3.8GHz - 100-100001015BOX - Socket: AM5 - Nº de núcleos de CPU: 6 - Nº de threads: 12 - Clock de Max Boost: Até 5.1GHz - Clock básico: 3.8GHz - Cache L1 total: 384KB - Cache L2 total: 6 MB - Cache L3 total: 32 MB - Cache Total: 38MB - TDP / TDP Padrão: 65W - Desbloqueado: Sim - Solução térmica (Cooler): AMD Wraith Stealth - Temps máx: 95°C - CMOS: TSMC 5nm FinFET - Versão do PCI Express: PCIe 5.0 - Memória - DDR5 - Velocidade máxima: 5200 MHz Gráficos integrados - Modelo Gráfico: AMD Radeon"""


def test_ryzen_7600_description():
    specs = extract_specs("PROCESSADOR", [], DESCRIPTION)
    assert specs["socket"] == "AM5"
    assert specs["nucleos"] == 6
    assert specs["threads"] == 12
    assert specs["frequenciaBaseMhz"] == 3800
    assert specs["frequenciaTurboMhz"] == 5100
    assert specs["cacheL2Mb"] == 6.0
    assert specs["cacheL3Mb"] == 32.0
    assert specs["tdpWatts"] == 65
    assert specs["tiposMemoriaSuportados"] == ["DDR5"]
    assert specs["frequenciaMemoriaMaximaMhz"] == 5200
    assert specs["temperaturaMaximaC"] == 95.0
    assert specs["versaoPcie"] == "5.0"
    assert specs["coolerIncluso"] is True
    assert specs["multiplicadorDesbloqueado"] is True
    assert "geracao" not in specs
