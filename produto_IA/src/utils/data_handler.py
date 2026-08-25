import csv
import json
from datetime import datetime
from pathlib import Path


class DataHandler:
    def __init__(self, data_dir="data/raw"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_json(self, data, filename="produto"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.data_dir / f"{filename}_{stamp}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

    def save_csv(self, data, filename="produto"):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.data_dir / f"{filename}_{stamp}.csv"
        row = data if isinstance(data, dict) else {"data": data}
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=row.keys())
            writer.writeheader()
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for k, v in row.items()})
        return str(path)
