import unittest

from src.extractors.backend_schemas import CATEGORY_SLUGS, SCHEMAS
from src.extractors.category import detect_category


class ElectronicsCategoryTest(unittest.TestCase):
    def test_detects_general_electronics(self):
        cases = {
            "Apple iPhone 17 Pro 256GB 5G": "CELULAR",
            "Samsung Galaxy Tab S11 tablet 256GB": "TABLET",
            "Sony PlayStation 5 Slim console videogame": "VIDEOGAME",
            "Robô aspirador inteligente com mapeamento laser": "ROBO_ASPIRADOR",
            "Aspirador de pó vertical 1600W": "ASPIRADOR_PO",
            "Câmera digital mirrorless Sony Alpha": "CAMERA",
            "Câmera de ação GoPro 4K": "CAMERA_ACAO",
            "Smart TV OLED 55 4K": "SMART_TV",
            "TV LED 43 4K UHD": "TV",
            "Echo Dot Smart Speaker Alexa": "SMART_SPEAKER",
            "Câmera de segurança Wi-Fi IP externa": "CAMERA_SEGURANCA",
            "Lâmpada inteligente Wi-Fi RGB": "LAMPADA_INTELIGENTE",
            "Air Fryer 5 litros 1700W": "AIR_FRYER",
            "Kindle e-reader 16GB": "E_READER",
            "Drone DJI com câmera 4K": "DRONE",
            "Kit Arduino robótica iniciante": "KIT_ARDUINO_ROBOTICA",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(detect_category(title), expected)

    def test_generic_categories_have_backend_contract(self):
        for category, slug in {
            "VIDEOGAME": "videogames-consoles",
            "KIT_ARDUINO_ROBOTICA": "kits-arduino-robotica",
            "ASPIRADOR_PO": "aspiradores-de-po",
            "ROBO_ASPIRADOR": "robos-aspiradores",
            "SMART_SPEAKER": "smart-speakers",
            "CAMERA_SEGURANCA": "cameras-de-seguranca",
            "AIR_FRYER": "air-fryers",
        }.items():
            with self.subTest(category=category):
                self.assertIn(category, SCHEMAS)
                self.assertEqual(SCHEMAS[category][0], "PRODUTO")
                self.assertEqual(CATEGORY_SLUGS[category], slug)


if __name__ == "__main__":
    unittest.main()
