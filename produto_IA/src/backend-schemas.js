const SCHEMAS = {
  PROCESSADOR: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoProcessador',
    campos: [
      'socket','familia','linha','geracao','arquitetura','litografiaNm','nucleos','threads',
      'frequenciaBaseMhz','frequenciaTurboMhz','cacheL2Mb','cacheL3Mb','tdpWatts',
      'possuiVideoIntegrado','modeloVideoIntegrado','tiposMemoriaSuportados',
      'frequenciaMemoriaMaximaMhz','capacidadeMemoriaMaximaGb','canaisMemoria','suportaEcc',
      'temperaturaMaximaC','versaoPcie','lanesPcie','coolerIncluso','multiplicadorDesbloqueado',
      'suporteOverclock','dataLancamento'
    ]
  },
  PLACA_MAE: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoPlacaMae',
    campos: [
      'socket','chipset','formato','revisao','biosInicial','tiposMemoriaSuportados',
      'formatosMemoriaSuportados','frequenciasMemoriaJedecMhz','frequenciasMemoriaOverclockMhz',
      'slotsMemoria','capacidadeMaximaMemoriaGb','capacidadeMaximaPorSlotGb','suportaXmp',
      'suportaExpo','suportaEcc','suportaMemoriaRegistrada','saidasVideo','portasSata','versaoPcie',
      'wifi','bluetooth','ethernet','biosFlashback','biosMinima','slotsM2'
    ]
  },
  MEMORIA_RAM: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoMemoriaRam',
    campos: [
      'tipo','formato','capacidadePorModuloGb','quantidadeModulos','frequenciaMhz','frequenciaJedecMhz',
      'latenciaCl','tensaoVolts','ecc','registrada','suportaXmp','suportaExpo','alturaMm','rgb','consumoWatts'
    ]
  },
  PLACA_VIDEO: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoPlacaVideo',
    campos: [
      'chipset','gpu','arquitetura','memoriaVideoGb','tipoMemoriaVideo','barramentoBits','clockBaseMhz',
      'clockBoostMhz','geracaoPcie','larguraPcie','comprimentoMm','alturaMm','espessuraMm','slotsOcupados',
      'consumoWatts','potenciaFonteRecomendadaWatts','conectoresPcie6Pinos','conectoresPcie8Pinos',
      'conectores12vhpwr','conectores12v2x6','saidasVideo','hdmi','displayPort'
    ]
  },
  ARMAZENAMENTO: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoArmazenamento',
    campos: [
      'tipo','formato','interface','capacidadeGb','tamanhoM2Mm','chaveM2','geracaoPcie','pistasPcie',
      'leituraSequencialMbps','escritaSequencialMbps','alturaMm','larguraMm','profundidadeMm','espessuraMm',
      'consumoWatts','possuiDissipador'
    ]
  },
  FONTE: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoFonte',
    campos: [
      'formato','potenciaWatts','certificacao','modularidade','comprimentoMm','larguraMm','alturaMm','padraoAtx',
      'eficienciaPercentual','correnteLinha12vAmperes','conectoresAtx24Pinos','conectoresEpsCpu',
      'conectoresPcie6Pinos','conectoresPcie8Pinos','conectores12vhpwr','conectores12v2x6','conectoresSata',
      'conectoresMolex','protecoes','tensaoEntrada'
    ]
  },
  GABINETE: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoGabinete',
    campos: [
      'tamanho','alturaMm','larguraMm','profundidadeMm','formatosPlacaMaeSuportados','formatosFonteSuportados',
      'comprimentoMaximoFonteMm','comprimentoMaximoGpuMm','alturaMaximaGpuMm','slotsMaximosGpu',
      'alturaMaximaCoolerCpuMm','baias25','baias35','slotsTraseiros','suportaGpuVertical',
      'espacoGerenciamentoCabosMm','suportesFans','suportesRadiador'
    ]
  },
  COOLER: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoCooler',
    campos: [
      'tipo','socketsSuportados','capacidadeTermicaWatts','alturaMm','larguraMm','profundidadeMm','alturaLivreRamMm',
      'tamanhoRadiadorMm','espessuraRadiadorMm','quantidadeVentoinhas','tamanhoVentoinhaMm','espessuraVentoinhaMm',
      'comprimentoMangueirasMm','conectorBomba','consumoBombaWatts','consumoWatts','ruidoDb','vidaUtilHoras',
      'pesoGramas','velocidadeMaxRpm','rgb','argb'
    ]
  },
  VENTOINHA: {
    tipoCadastro: 'HARDWARE',
    campo: 'especificacaoVentoinha',
    campos: [
      'tamanhoMm','espessuraMm','rpmMinima','rpmMaxima','fluxoArCfm','pressaoEstaticaMmH2o','ruidoDb',
      'conector','tensaoVolts','correnteAmperes','pwm','rgb','argb','fluxoReverso'
    ]
  },
  MONITOR: {
    tipoCadastro: 'PRODUTO',
    campo: 'especificacaoMonitor',
    campos: [
      'tamanhoPolegadas','resolucao','taxaAtualizacaoHz','tipoPainel','tempoRespostaMs','brilhoNits','hdr',
      'adaptiveSync','gSync','freeSync','hdmi','displayPort','usbC','vesa'
    ]
  },
  MOUSE: {
    tipoCadastro: 'PRODUTO',
    campo: 'especificacaoMouse',
    campos: ['sensor','dpiMaximo','pollingRateHz','botoes','pesoGramas','conexao','bluetooth','wireless','cabo','rgb','mao']
  },
  TECLADO: {
    tipoCadastro: 'PRODUTO',
    campo: 'especificacaoTeclado',
    campos: ['tipo','layout','switch','tamanho','abnt2','conexao','bluetooth','wireless','usb','rgb','hotSwap']
  },
  FONE: {
    tipoCadastro: 'PRODUTO',
    campo: 'especificacaoHeadset',
    campos: ['tipoConexao','wireless','bluetooth','driverMm','microfone','somSurround','impedancia','pesoGramas','bateriaHoras']
  },
  MICROFONE: {
    tipoCadastro: 'PRODUTO',
    campo: null,
    campos: []
  },
  NOTEBOOK: {
    tipoCadastro: 'NOTEBOOK',
    campo: 'especificacao',
    campos: [
      'processadorNome','processadorMarca','processadorGeracao','nucleos','threads','clockBaseMhz','clockTurboMhz',
      'tdpWatts','gpuNome','gpuIntegrada','gpuDedicada','vramGb','tgpWatts','ramInstaladaGb','tipoMemoria',
      'frequenciaMhz','ramSoldadaGb','slotsRamTotal','slotsRamLivres','ramMaximaGb','upgradeRam','armazenamentoGb',
      'tipoArmazenamento','slotsM2Total','slotsM2Livres','upgradeArmazenamento','tamanhoTelaPolegadas','resolucaoLargura',
      'resolucaoAltura','taxaAtualizacaoHz','tipoPainel','brilhoNits','touch','bateriaWh','autonomiaInformadaHoras',
      'potenciaCarregadorWatts','pesoKg','larguraMm','alturaMm','profundidadeMm','wifi','bluetooth','usbA','usbC',
      'thunderbolt','hdmi','displayPort','ethernet','leitorCartao','sistemaOperacional','webcam','resolucaoWebcam',
      'tecladoIluminado','tecladoNumerico','leitorDigital'
    ]
  }
};

const ENUMS = {
  TipoMemoria: ['DDR3','DDR4','DDR5'],
  FormatoMemoria: ['DIMM','SO_DIMM'],
  FormatoPlacaMae: ['E_ATX','ATX','MICRO_ATX','MINI_ITX'],
  TamanhoGabinete: ['FULL_TOWER','MID_TOWER','MINI_TOWER','SFF','OPEN_FRAME'],
  FormatoFonte: ['ATX','SFX','SFX_L','TFX','FLEX_ATX'],
  ModularidadeFonte: ['NAO_MODULAR','SEMI_MODULAR','MODULAR'],
  TipoCooler: ['AIR_COOLER','WATER_COOLER'],
  TipoConectorVentoinha: ['DC_3_PINOS','PWM_4_PINOS','MOLEX','PROPRIETARIO'],
  TipoArmazenamento: ['SSD','HDD'],
  FormatoArmazenamento: ['POLEGADAS_2_5','POLEGADAS_3_5','M2','PLACA_PCIE'],
  InterfaceArmazenamento: ['SATA','NVME_PCIE','SAS'],
  ChaveM2: ['B','M','B_M']
};

module.exports = { SCHEMAS, ENUMS };
