from src.build_detection.analyzer import analyze_listing


def test_pc_computador_com_cpu_ssd_ram_no_titulo_sem_descricao():
    resultado = analyze_listing(
        'PC Computador CPU Intel Core i7 3,4GHz SSD 480GB 16GB 500W',
        '',
    )
    assert resultado['tipoSugerido'] == 'PC_MONTADO'
    categorias = {item['categoria'] for item in resultado['componentesDetectados']}
    assert 'PROCESSADOR' in categorias
    assert 'ARMAZENAMENTO' in categorias
    assert resultado['descricaoOriginal'] == ''


def test_computador_apenas_uma_peca_sem_descricao_nao_e_pc_confirmado():
    resultado = analyze_listing('Computador Intel Core i7', '')
    assert resultado['tipoSugerido'] != 'PC_MONTADO'


def test_kit_upgrade_continua_kit_com_componentes_no_titulo():
    resultado = analyze_listing('Kit Upgrade Processador Ryzen 5 Placa Mãe B550 Memória 16GB', '')
    assert resultado['tipoSugerido'] == 'KIT_UPGRADE'


def test_anuncio_sem_gabinete_nao_classifica_como_pc_completo():
    resultado = analyze_listing('PC Intel Core i7 SSD 480GB', 'Sem gabinete e sem fonte')
    assert resultado['tipoSugerido'] != 'PC_MONTADO'


def test_teclado_mouse_ficam_somente_na_descricao():
    resultado = analyze_listing(
        'PC Computador Intel Core i7 SSD 480GB',
        'Acompanha teclado e mouse. Processador Intel Core i7.',
    )
    assert resultado['tipoSugerido'] == 'PC_MONTADO'
    assert set(resultado['acessoriosNaDescricao']) == {'teclado', 'mouse'}
    assert all(item['categoria'] not in {'TECLADO', 'MOUSE'} for item in resultado['componentesDetectados'])
