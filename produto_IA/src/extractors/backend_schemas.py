SCHEMAS = {
    "PROCESSADOR": ("HARDWARE", "especificacaoProcessador", [
        "socket", "familia", "linha", "geracao", "arquitetura", "litografiaNm", "nucleos", "threads",
        "frequenciaBaseMhz", "frequenciaTurboMhz", "cacheL2Mb", "cacheL3Mb", "tdpWatts",
        "possuiVideoIntegrado", "modeloVideoIntegrado", "tiposMemoriaSuportados", "frequenciaMemoriaMaximaMhz",
        "capacidadeMemoriaMaximaGb", "canaisMemoria", "suportaEcc", "temperaturaMaximaC", "versaoPcie",
        "lanesPcie", "coolerIncluso", "multiplicadorDesbloqueado", "suporteOverclock", "dataLancamento"
    ]),
    "PLACA_MAE": ("HARDWARE", "especificacaoPlacaMae", [
        "socket", "chipset", "formato", "revisao", "biosInicial", "tiposMemoriaSuportados", "formatosMemoriaSuportados",
        "frequenciasMemoriaJedecMhz", "frequenciasMemoriaOverclockMhz", "slotsMemoria", "capacidadeMaximaMemoriaGb",
        "capacidadeMaximaPorSlotGb", "suportaXmp", "suportaExpo", "suportaEcc", "suportaMemoriaRegistrada", "saidasVideo",
        "portasSata", "versaoPcie", "wifi", "bluetooth", "ethernet", "biosFlashback", "biosMinima", "slotsM2"
    ]),
    "MEMORIA_RAM": ("HARDWARE", "especificacaoMemoriaRam", [
        "tipo", "formato", "capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz", "frequenciaJedecMhz",
        "latenciaCl", "tensaoVolts", "ecc", "registrada", "suportaXmp", "suportaExpo", "alturaMm", "rgb", "consumoWatts"
    ]),
    "PLACA_VIDEO": ("HARDWARE", "especificacaoPlacaVideo", [
        "chipset", "gpu", "arquitetura", "memoriaVideoGb", "tipoMemoriaVideo", "barramentoBits", "clockBaseMhz",
        "clockBoostMhz", "geracaoPcie", "larguraPcie", "comprimentoMm", "alturaMm", "espessuraMm", "slotsOcupados",
        "consumoWatts", "potenciaFonteRecomendadaWatts", "conectoresPcie6Pinos", "conectoresPcie8Pinos", "conectores12vhpwr",
        "conectores12v2x6", "saidasVideo", "hdmi", "displayPort"
    ]),
    "ARMAZENAMENTO": ("HARDWARE", "especificacaoArmazenamento", [
        "tipo", "formato", "interface", "capacidadeGb", "tamanhoM2Mm", "chaveM2", "geracaoPcie", "pistasPcie",
        "leituraSequencialMbps", "escritaSequencialMbps", "alturaMm", "larguraMm", "profundidadeMm", "espessuraMm",
        "consumoWatts", "possuiDissipador"
    ]),
    "FONTE": ("HARDWARE", "especificacaoFonte", ["formato", "potenciaWatts", "certificacao", "modularidade"]),
    "GABINETE": ("HARDWARE", "especificacaoGabinete", ["tamanho", "alturaMm", "larguraMm", "profundidadeMm"]),
    "COOLER": ("HARDWARE", "especificacaoCooler", ["tipo", "socketsSuportados", "capacidadeTermicaWatts", "alturaMm", "rgb"]),
    "VENTOINHA": ("HARDWARE", "especificacaoVentoinha", ["tamanhoMm", "rpmMinima", "rpmMaxima", "fluxoArCfm", "ruidoDb", "conector", "pwm", "rgb", "argb"]),
    "MONITOR": ("PRODUTO", "especificacaoMonitor", ["tamanhoPolegadas", "resolucao", "taxaAtualizacaoHz", "tipoPainel"]),
    "MOUSE": ("PRODUTO", "especificacaoMouse", ["sensor", "dpiMaximo", "pollingRateHz", "botoes", "conexao", "rgb"]),
    "TECLADO": ("PRODUTO", "especificacaoTeclado", ["tipo", "layout", "switch", "tamanho", "abnt2", "conexao", "bluetooth", "wireless", "usb", "rgb", "hotSwap"]),
    "FONE": ("PRODUTO", "especificacaoHeadset", ["tipoConexao", "wireless", "bluetooth", "driverMm", "microfone", "somSurround"]),
    "MICROFONE": ("PRODUTO", None, []),
}

REQUIRED = {
    "PROCESSADOR": ["socket", "tiposMemoriaSuportados"],
    "PLACA_MAE": ["socket", "chipset", "formato", "tiposMemoriaSuportados", "slotsMemoria"],
    "MEMORIA_RAM": ["tipo", "formato", "capacidadePorModuloGb", "quantidadeModulos", "frequenciaMhz"],
    "PLACA_VIDEO": ["comprimentoMm"],
    "ARMAZENAMENTO": ["tipo", "formato", "interface", "capacidadeGb"],
    "FONTE": ["formato", "potenciaWatts"],
    "GABINETE": ["tamanho", "alturaMm", "larguraMm", "profundidadeMm"],
    "COOLER": ["tipo", "socketsSuportados"],
    "VENTOINHA": ["tamanhoMm", "conector"],
}
