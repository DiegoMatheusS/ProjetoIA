import hashlib
import json
import unittest

from src.shopee.agent import ShopeeAffiliateAgent
from src.shopee.client import ShopeeAffiliateClient


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


class ShopeeAffiliateClientTest(unittest.TestCase):
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
    def test_agent_prioritizes_matching_hardware(self):
        result = ShopeeAffiliateAgent(FakeShopeeClient()).find_products(query="RTX 5070", limit=20)
        self.assertEqual(result["itens"][0]["itemId"], "1")
        self.assertEqual(result["fontePrimaria"], "SHOPEE_AFFILIATE_API")
        self.assertFalse(result["scrapingNecessario"])

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
