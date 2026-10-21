import hashlib
import json
import unittest

from src.shopee.agent import ShopeeAffiliateAgent, extract_shopee_ids, is_shopee_url
from src.shopee.client import ShopeeAffiliateClient
from src.main import build_result


class FakeShopeeClient:
    configured = True

    def search_products(self, **kwargs):
        return {
            "itens": [
                {
                    "itemId": "2",
                    "shopId": "20",
                    "nome": "Cabo USB comum",
                    "preco": 20.0,
                    "descontoPercentual": 0,
                    "emPromocao": False,
                    "vendas": 9000,
                    "avaliacao": 4.9,
                },
                {
                    "itemId": "1",
                    "shopId": "10",
                    "nome": "ASUS TUF RTX 5070 12GB",
                    "preco": 4299.0,
                    "descontoPercentual": 12,
                    "emPromocao": True,
                    "vendas": 350,
                    "avaliacao": 4.8,
                },
            ],
            "pagina": {"page": 1, "hasNextPage": False},
        }

    def list_campaigns(self, **kwargs):
        return {"itens": [{"nome": "Oferta Tech"}], "pagina": {"page": 1}}


class ShopeeUrlTest(unittest.TestCase):
    def test_recognizes_shopee_br_hosts(self):
        self.assertTrue(is_shopee_url("https://shopee.com.br/produto-i.10.20"))
        self.assertTrue(is_shopee_url("https://s.shopee.com.br/abc"))
        self.assertFalse(is_shopee_url("https://example.com/produto-i.10.20"))

    def test_extracts_ids_from_slug_url(self):
        self.assertEqual(
            extract_shopee_ids("https://shopee.com.br/RTX-5070-i.12345.987654321"),
            (12345, 987654321),
        )

    def test_extracts_ids_from_product_url(self):
        self.assertEqual(
            extract_shopee_ids("https://shopee.com.br/product/12345/987654321"),
            (12345, 987654321),
        )


    def test_build_result_preserves_affiliate_link_and_marketplace(self):
        result = build_result(
            {
                "ok": True,
                "source": "SHOPEE_AFFILIATE_API",
                "api_used": True,
                "url_original": "https://shopee.com.br/RTX-5070-i.12345.987654321",
                "url_final": "https://shopee.com.br/RTX-5070-i.12345.987654321",
                "affiliate_url": "https://s.shopee.com.br/abc123",
                "title": "ASUS TUF RTX 5070 12GB",
                "price": 3999.9,
                "attributes": [],
            }
        )
        self.assertEqual(result["marketplace"]["plataforma"], "SHOPEE")
        self.assertTrue(result["marketplace"]["apiUsada"])
        self.assertEqual(
            result["ofertaColetada"]["urlAfiliada"],
            "https://s.shopee.com.br/abc123",
        )


class ShopeeAffiliateClientTest(unittest.TestCase):
    def test_product_query_caps_upstream_page_limit_at_fifty(self):
        client = ShopeeAffiliateClient(app_id='123', secret='test')
        queries = []
        def graphql(query, **kwargs):
            queries.append(query)
            return {'productOfferV2': {'nodes': [], 'pageInfo': {}}}
        client.graphql = graphql
        client.search_products(keyword='placa de vídeo', limit=60)
        self.assertIn('limit: 50', queries[0])
        self.assertNotIn('limit: 60', queries[0])
    def test_signature_uses_exact_serialized_payload(self):
        client = ShopeeAffiliateClient(app_id="123", secret="segredo")
        payload = {"query": "query { ping }"}
        serialized = client.serialize_payload(payload)
        expected = hashlib.sha256(f"1231700000000{serialized}segredo".encode()).hexdigest()
        self.assertEqual(client.signature(1700000000, serialized), expected)

    def test_payload_serialization_is_compact_and_deterministic(self):
        payload = {"query": "query { produto }", "variables": {"q": "placa de vídeo"}}
        serialized = ShopeeAffiliateClient.serialize_payload(payload)
        self.assertEqual(
            serialized,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        )

    def test_normalizes_product_and_promotion(self):
        item = ShopeeAffiliateClient.normalize_product(
            {
                "itemId": 99,
                "productName": "RTX 5070",
                "priceMin": "3999.90",
                "priceMax": "4299.90",
                "priceDiscountRate": "0.15",
                "commissionRate": "0.0850",
                "sellerCommissionRate": "0.05",
                "shopeeCommissionRate": "0.035",
                "sales": "20",
                "ratingStar": "4.8",
            }
        )
        self.assertEqual(item["itemId"], "99")
        self.assertEqual(item["preco"], 3999.90)
        self.assertEqual(item["descontoPercentual"], 15.0)
        self.assertEqual(item["comissaoPercentual"], 8.5)
        self.assertEqual(item["comissaoSellerPercentual"], 5.0)
        self.assertEqual(item["comissaoShopeePercentual"], 3.5000000000000004)
        self.assertTrue(item["emPromocao"])
        self.assertTrue(item["apiOficial"])


class ShopeeAffiliateAgentTest(unittest.TestCase):
    def test_generic_gpu_search_expands_to_model_families_when_original_has_only_accessories(self):
        class Client(FakeShopeeClient):
            def search_products(self, **kwargs):
                if kwargs['keyword'] == 'RTX':
                    items = [{'itemId': '2', 'nome': 'ASUS RTX 4060'}]
                elif kwargs['keyword'] == 'Radeon RX':
                    items = [{'itemId': '3', 'nome': 'Sapphire Radeon RX 6600'}]
                else:
                    items = [{'itemId': '1', 'nome': 'Suporte para placa de vídeo'}]
                return {'itens': items, 'pagina': {'hasNextPage': False}}
        result = ShopeeAffiliateAgent(Client()).find_products(query='placa de vídeo')
        self.assertEqual({item['itemId'] for item in result['itens']}, {'2', '3'})
        self.assertEqual(result['pagina']['paginasConsultadas'], 3)

    def test_generic_gpu_search_excludes_supports_cables_and_complete_pcs(self):
        class Client(FakeShopeeClient):
            def search_products(self, **kwargs):
                return {'itens': [
                    {'itemId': '1', 'nome': 'Suporte para placa de vídeo RTX 4060', 'vendas': 90000},
                    {'itemId': '2', 'nome': 'Cabo riser PCIe para GPU'},
                    {'itemId': '3', 'nome': 'ASUS RTX 4060 8GB Dual Fan com suporte'},
                    {'itemId': '4', 'nome': 'Placa de Vídeo Radeon RX 6600 8GB'},
                    {'itemId': '5', 'nome': 'PC Gamer RTX 4060 completo'},
                ], 'pagina': {'hasNextPage': False}}
        result = ShopeeAffiliateAgent(Client()).find_products(query='placa de vídeo', limit=60)
        self.assertEqual({item['itemId'] for item in result['itens']}, {'3', '4'})
        self.assertEqual(result['categoriaBusca'], 'GPU')
        self.assertEqual(result['itensDescartados'], 3)

    def test_accessory_search_still_finds_accessories(self):
        from src.shopee.relevance import search_intent, relevant_item
        query = 'suporte para placa de vídeo'
        self.assertEqual(search_intent(query), 'SUPPORT')
        self.assertTrue(relevant_item({'nome': 'Suporte para GPU'}, query, search_intent(query)))
        self.assertFalse(relevant_item({'nome': 'Suporte para monitor'}, query, search_intent(query)))
        self.assertFalse(relevant_item({'nome': 'ASUS RTX 4060'}, query, search_intent(query)))

    def test_search_filters_primary_product_across_categories(self):
        cases = [
            ('processador', 'AMD Ryzen 5 5500 processador com cooler', 'Cooler para processador Ryzen', 'Placa mãe para Ryzen 5 5500'),
            ('placa mãe', 'Placa-mãe ASUS B550 DDR4 Ryzen', 'Cabo para placa mãe', 'Kit upgrade Ryzen placa mãe RAM'),
            ('memória RAM', 'Memória DDR4 16GB para notebook', 'Dissipador para memória RAM', 'Notebook com memória RAM 16GB'),
            ('SSD', 'Kingston SSD NVMe 1TB', 'Case para SSD NVMe', 'Cabo SATA para SSD'),
            ('HD', 'HD externo Seagate 1TB', 'Case para HD externo', 'SSD 1TB'),
            ('fonte', 'Fonte ATX Corsair 650W com cabo', 'Cabo para fonte ATX', 'Gabinete PC com fonte 650W'),
            ('gabinete', 'Gabinete gamer ATX com fans', 'Suporte para gabinete', 'PC gamer com gabinete RGB'),
            ('cooler', 'Cooler para processador Ryzen', 'Suporte para cooler', 'Processador Ryzen com cooler'),
            ('ventoinha', 'Ventoinha ARGB 120mm', 'Cabo para ventoinha', 'Gabinete com ventoinha 120mm'),
            ('monitor', 'Full HD Monitor gamer 27 com suporte e cabo', 'Suporte para monitor', 'Cabo HDMI para monitor', 'Braço articulado para monitor'),
            ('notebook', 'Notebook Dell i5 16GB SSD', 'Carregador para notebook Dell', 'Memória RAM para notebook'),
            ('mouse', 'Mouse Logitech gamer com mousepad', 'Mousepad para mouse gamer', 'Suporte para mouse'),
            ('teclado', 'Teclado mecânico gamer com capa', 'Capa para teclado mecânico', 'Kit de cabo para teclado'),
            ('headset', 'Headset gamer com microfone', 'Suporte para headset gamer', 'Cabo para headset'),
            ('microfone', 'Microfone USB com suporte', 'Suporte para microfone', 'Headset com microfone'),
            ('TV', 'Smart TV 50 LED', 'Suporte para TV 50', 'Controle para TV'),
            ('celular', 'Celular Samsung Galaxy', 'Capa para celular Samsung', 'Suporte para celular'),
            ('cadeira', 'Cadeira gamer com apoio', 'Capa para cadeira gamer', 'Suporte para cadeira'),
            ('adaptador HDMI', 'Adaptador HDMI VGA', 'Cabo HDMI', 'Monitor HDMI'),
            ('cabo USB', 'Cabo USB para teclado', 'Teclado USB com cabo', 'Adaptador USB'),
            ('mousepad', 'Mousepad gamer', 'Mouse gamer com mousepad', 'Teclado gamer'),
        ]
        from src.shopee.relevance import search_intent, relevant_item
        for query, correct, *incorrect in cases:
            with self.subTest(query=query):
                intent = search_intent(query)
                self.assertIsNotNone(intent)
                self.assertTrue(relevant_item({'nome': correct}, query, intent), correct)
                for title in incorrect:
                    self.assertFalse(relevant_item({'nome': title}, query, intent), title)

    def test_models_capacities_brands_and_unknown_queries_are_required(self):
        from src.shopee.relevance import search_intent, relevant_item
        cases = [
            ('RTX4060Ti', 'ASUS RTX 4060 Ti 8GB', 'ASUS RTX 4060 8GB'),
            ('pc case', 'PC Case ATX RGB', 'PC gamer completo'),
            ('SSD 1TB', 'SSD NVMe Kingston 1 TB', 'SSD Kingston 480GB'),
            ('memória DDR4 16GB', 'Memória RAM DDR4 16 GB', 'Memória RAM DDR5 16GB'),
            ('Ryzen 5 5500', 'Processador AMD Ryzen 5 5500', 'Processador AMD Ryzen 5 5600'),
            ('core i5', 'Intel Core i5 12400F', 'Intel Core i7 12700F'),
            ('mouse Logitech G502', 'Logitech G502 Mouse gamer', 'Logitech G203 Mouse gamer'),
            ('teclado sem fio', 'Teclado wireless', 'Teclado USB com fio'),
            ('cafeteira elétrica', 'Cafeteira elétrica 1L', 'Filtro para cafeteira'),
            ('cafeteira', 'Cafeteira elétrica 1L com cabo', 'Cabo para cafeteira elétrica'),
        ]
        for query, correct, incorrect in cases:
            with self.subTest(query=query):
                self.assertTrue(relevant_item({'nome': correct}, query, search_intent(query)))
                self.assertFalse(relevant_item({'nome': incorrect}, query, search_intent(query)))

    def test_sixty_results_are_collected_in_valid_pages_without_duplicates(self):
        class Client(FakeShopeeClient):
            def __init__(self):
                self.calls = []
            def search_products(self, **kwargs):
                self.calls.append(kwargs)
                self.assert_limit(kwargs['limit'])
                start = (kwargs['page'] - 1) * 50
                return {'itens': [{'itemId': str(i), 'nome': 'Placa de vídeo RTX 4060'} for i in range(start, start + 50)],
                        'pagina': {'page': kwargs['page'], 'hasNextPage': kwargs['page'] < 2}}
            def assert_limit(self, limit):
                if limit > 50:
                    raise AssertionError('Invalid limit')
        client = Client()
        result = ShopeeAffiliateAgent(client).find_products(query='placa de video', limit=60)
        self.assertEqual(len(result['itens']), 60)
        self.assertEqual([call['page'] for call in client.calls], [1, 2])
        self.assertEqual(len({item['itemId'] for item in result['itens']}), 60)

    def test_search_continues_after_accessory_only_page_and_preserves_partial_on_failure(self):
        from src.shopee.client import ShopeeAffiliateError
        class Client(FakeShopeeClient):
            def search_products(self, **kwargs):
                if kwargs['keyword'] != 'placa de vídeo':
                    raise ShopeeAffiliateError('upstream failure')
                if kwargs['page'] == 1:
                    return {'itens': [{'itemId': '1', 'nome': 'Suporte para placa de vídeo'}], 'pagina': {'hasNextPage': True}}
                if kwargs['page'] == 2:
                    return {'itens': [{'itemId': '2', 'nome': 'RTX 4060 8GB'}], 'pagina': {'hasNextPage': True}}
                raise ShopeeAffiliateError('upstream failure')
        result = ShopeeAffiliateAgent(Client()).find_products(query='placa de vídeo', limit=60)
        self.assertEqual([item['itemId'] for item in result['itens']], ['2'])
        self.assertTrue(result['avisos'])

    def test_repeated_page_stops_and_model_search_preserves_gpu_suffix(self):
        from src.shopee.relevance import search_intent, relevant_item
        for title in ['ASUS RTX 4060 Ti', 'ASUS RTX 4060 SUPER', 'ASUS RTX 4070']:
            self.assertFalse(relevant_item({'nome': title}, 'RTX 4060', search_intent('RTX 4060')))
        class Client(FakeShopeeClient):
            def __init__(self): self.calls = 0
            def search_products(self, **kwargs):
                self.calls += 1
                return {'itens': [{'itemId': '1', 'nome': 'RTX 4060'}], 'pagina': {'hasNextPage': True}}
        client = Client()
        result = ShopeeAffiliateAgent(client).find_products(query='RTX 4060', limit=60)
        self.assertEqual(len(result['itens']), 1)
        self.assertEqual(client.calls, 2)

    def test_agent_prioritizes_matching_hardware(self):
        result = ShopeeAffiliateAgent(FakeShopeeClient()).find_products(query="RTX 5070", limit=20)
        self.assertEqual(result["itens"][0]["itemId"], "1")
        self.assertEqual(result["fontePrimaria"], "SHOPEE_AFFILIATE_API")
        self.assertFalse(result["scrapingNecessario"])

    def test_agent_resolves_exact_product_from_url(self):
        item = ShopeeAffiliateAgent(FakeShopeeClient()).find_product_by_url(
            "https://shopee.com.br/ASUS-TUF-RTX-5070-i.10.1"
        )
        self.assertIsNotNone(item)
        self.assertEqual(item["itemId"], "1")
        self.assertEqual(item["shopId"], "10")

    def test_agent_can_filter_only_promotions(self):
        result = ShopeeAffiliateAgent(FakeShopeeClient()).find_products(
            query="RTX 5070",
            promotions_only=True,
        )
        self.assertEqual([item["itemId"] for item in result["itens"]], ["1"])

    def test_agent_can_select_exact_item_and_shop(self):
        result = ShopeeAffiliateAgent(FakeShopeeClient()).find_products(
            item_id=1,
            shop_id=10,
        )
        self.assertEqual([item["itemId"] for item in result["itens"]], ["1"])
        self.assertEqual(result["itemId"], "1")
        self.assertEqual(result["shopId"], "10")


if __name__ == "__main__":
    unittest.main()
