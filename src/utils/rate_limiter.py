import hashlib
import json
import os
import random
import threading
import time
from pathlib import Path
from urllib.parse import urlparse


class PoliteRateLimiter:
    """Limite simples por host para evitar rajadas de requisições.

    O projeto recebe URLs individuais; não é um crawler em massa. Ainda assim,
    cada host recebe uma pausa mínima + jitter antes da próxima chamada.
    """

    _lock = threading.Lock()
    _last_request_by_host = {}

    def __init__(self, min_delay=None, jitter=None):
        self.min_delay = float(
            min_delay if min_delay is not None else os.getenv("REQUEST_MIN_DELAY_SECONDS", "1.25")
        )
        self.jitter = float(
            jitter if jitter is not None else os.getenv("REQUEST_JITTER_SECONDS", "0.45")
        )

    def wait(self, url: str):
        host = (urlparse(url).hostname or "global").lower()
        target_gap = max(0.0, self.min_delay) + random.uniform(0.0, max(0.0, self.jitter))
        with self._lock:
            now = time.monotonic()
            last = self._last_request_by_host.get(host)
            sleep_for = max(0.0, target_gap - (now - last)) if last is not None else 0.0
            if sleep_for > 0:
                time.sleep(sleep_for)
            self._last_request_by_host[host] = time.monotonic()


class JsonDiskCache:
    """Cache curto de GETs para evitar repetir chamadas quando o mesmo URL é testado."""

    def __init__(self, base_dir=None):
        root = base_dir or os.getenv("HTTP_CACHE_DIR", ".cache/produto_ia_http")
        self.base_dir = Path(root)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(url, params=None, namespace="default"):
        payload = json.dumps(
            {"url": url, "params": params or {}, "namespace": namespace},
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, url, params=None, namespace="default", ttl_seconds=300):
        if ttl_seconds <= 0:
            return None
        path = self.base_dir / f"{self._key(url, params, namespace)}.json"
        try:
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
            created_at = float(data.get("created_at", 0))
            if time.time() - created_at > ttl_seconds:
                path.unlink(missing_ok=True)
                return None
            return data.get("payload")
        except Exception:
            return None

    def set(self, url, payload, params=None, namespace="default"):
        path = self.base_dir / f"{self._key(url, params, namespace)}.json"
        temp = path.with_suffix(".tmp")
        try:
            temp.write_text(
                json.dumps({"created_at": time.time(), "payload": payload}, ensure_ascii=False),
                encoding="utf-8",
            )
            temp.replace(path)
        except Exception:
            temp.unlink(missing_ok=True)
