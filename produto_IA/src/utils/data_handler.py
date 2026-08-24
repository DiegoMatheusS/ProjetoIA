import json
import pandas as pd
from datetime import datetime
from pathlib import Path
from loguru import logger

class DataHandler:
    def __init__(self, data_dir='data/raw'):
        self.data_dir = Path(data_dir)
        # CORREÇÃO: exist_ok=True impede o erro "File exists"
        self.data_dir.mkdir(parents=True, exist_ok=True)  # ← ESSA LINHA É CRUCIAL!
        
    def save_json(self, data, filename):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"{filename}_{timestamp}.json"
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Dados salvos em: {filepath}")
        return str(filepath)
        
    def save_csv(self, data, filename):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.data_dir / f"{filename}_{timestamp}.csv"
        df = pd.DataFrame([data]) if isinstance(data, dict) else pd.DataFrame(data)
        df.to_csv(filepath, index=False, encoding='utf-8')
        logger.info(f"Dados salvos em: {filepath}")
        return str(filepath)
        
    def load_json(self, filename):
        filepath = self.data_dir / f"{filename}.json"
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def list_files(self):
        return list(self.data_dir.glob("*"))