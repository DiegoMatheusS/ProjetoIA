import pytest
from src.catalog_specs import technical_attribute, technical_attributes
from src.main import build_result

@pytest.mark.parametrize('key,value', [
 ('Avaliações de clientes', "4,7 de 5 estrelas var dpAcrHasRegisteredArcLinkClickAction; P.when('A', 'ready').execute(function(A) {});"),
 ('Ranking dos mais vendidos', '#1 em cartuchos'), ('Best Sellers Rank', '#1 in ink'),
 ('Prazo', '2 dias'), ('Parcelas', '10x de R$ 10'), ('Preço', '99,90'),
 ('Customer Reviews', '4.7 out of 5 stars'), ('avaliacaoClientes', '4,7'),
 ('shippingCost', 10), ('Prazo de entrega', 'Amanhã'),
 ('Material', 'Plástico; window.ue.count("test")'),
])
def test_discards_commercial_fields_and_scripts(key,value):
 assert not technical_attribute(key,value)

@pytest.mark.parametrize('key,value', [
 ('Material', 'Plástico'), ('Rank', 'Dual Rank'), ('Cor', 'Preto'), ('Modelo', 'F6V29AB'),
 ('Capacidade', '2 ml'), ('Compatibilidade', 'HP DeskJet 2136, 2676, 3776'),
 ('Rendimento de páginas', '120 páginas'), ('Duplex', False), ('Consumo em espera', 0),
 ('Composição', ['Polipropileno', 'Tinta pigmentada']),
])
def test_keeps_technical_data_including_false_and_zero(key,value):
 assert technical_attribute(key,value)

def test_generic_registration_preserves_technical_rows_without_shop_information():
 rows=[{'name':'Material','value_name':'Plástico'},{'name':'Cor','value_name':'Preto'},
       {'name':'Avaliações de clientes','value_name':'4,7 de 5 estrelas'},
       {'name':'Parcelas','value_name':'12x sem juros'}]
 result=build_result({'title':'Cartucho HP 664 F6V29AB', 'attributes':rows,'product_attributes':rows},forced_category='ACESSORIO')
 assert result['informacoesProdutoEncontradas']==rows[:2]
 assert result['payloadParcialBackend']['metadados']['informacoesProdutoEncontradas']==rows[:2]


def test_marketplace_attribute_id_is_preserved_without_a_display_name():
 rows=[{'id':'OPERATING_SYSTEM','value_name':'Linux'}, {'id':'RAM_MEMORY','value_name':'16 GB'}]
 assert technical_attributes(rows)==rows
