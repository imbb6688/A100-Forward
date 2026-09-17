from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import requests


BASE_URL = "https://fuyao.aicubes.cn"
INDEX_CATALOG_ENDPOINT = "/api/a-share-index/catalog/ths-index-list"
INDEX_CONSTITUENTS_ENDPOINT = "/api/a-share-index/constituents/ths-stock-list"
DRAGON_TIGER_ENDPOINT = "/api/a-share/special-data/dragon-tiger-list"
ANOMALY_STOCK_ENDPOINT = "/api/a-share/special-data/anomaly-analysis-stock"
LIMIT_UP_POOL_ENDPOINT = "/api/a-share/special-data/limit-up-pool"
LIMIT_DOWN_POOL_ENDPOINT = "/api/a-share/special-data/limit-down-pool"
LIMIT_BREAK_POOL_ENDPOINT = "/api/a-share/special-data/limit-break-pool"

INDEX_TAGS = {"cn_concept", "region", "tszs", "industry"}
DRAGON_TIGER_BOARD_TYPES = {"all", "org", "hot_money"}


@dataclass(frozen=True)
class HiThinkSecurityEventBundle:
    ticker: str
    anomaly: Dict[str, Any]
    dragon_tiger: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "anomaly": dict(self.anomaly),
            "dragon_tiger": dict(self.dragon_tiger),
        }


class HiThinkContextClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = BASE_URL,
        timeout: float = 30.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must not be empty")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.session = session or requests.Session()

    def _get(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        response = self.session.get(
            self.base_url + endpoint,
            params={k: v for k, v in params.items() if v is not None},
            headers={"X-api-key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("HiThink response must be a JSON object")
        code = payload.get("code")
        if code not in (0, "0", None):
            raise RuntimeError(
                f"HiThink API error code={code}, message={payload.get('message')!r}, request_id={payload.get('request_id')!r}"
            )
        data = payload.get("data")
        return {} if data is None else dict(data)

    @staticmethod
    def _items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = data.get("item", [])
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise ValueError("HiThink data.item must be a list")
        return [dict(row) for row in raw if isinstance(row, dict)]

    def index_catalog(self, tag: str = "industry") -> List[Dict[str, Any]]:
        normalized = tag.strip().lower()
        if normalized not in INDEX_TAGS:
            raise ValueError(f"tag must be one of {sorted(INDEX_TAGS)}")
        return self._items(self._get(INDEX_CATALOG_ENDPOINT, {"tag": normalized}))

    def index_constituents(self, thscode: str) -> List[Dict[str, Any]]:
        code = thscode.strip().upper()
        if not code or "." not in code:
            raise ValueError("index thscode must include exchange suffix")
        return self._items(self._get(INDEX_CONSTITUENTS_ENDPOINT, {"thscode": code}))

    def anomaly_for_stocks(self, thscodes: Iterable[str]) -> Dict[str, Any]:
        codes = [str(code).strip().upper() for code in thscodes if str(code).strip()]
        if not 1 <= len(codes) <= 50:
            raise ValueError("thscodes must contain between 1 and 50 symbols")
        return self._get(ANOMALY_STOCK_ENDPOINT, {"thscodes": ",".join(codes)})

    def dragon_tiger(self, *, board_type: str = "all", date: Optional[str] = None) -> Dict[str, Any]:
        board = board_type.strip().lower()
        if board not in DRAGON_TIGER_BOARD_TYPES:
            raise ValueError(f"board_type must be one of {sorted(DRAGON_TIGER_BOARD_TYPES)}")
        return self._get(DRAGON_TIGER_ENDPOINT, {"board_type": board, "date": date})

    def limit_pool(self, kind: str) -> Dict[str, Any]:
        mapping = {
            "up": LIMIT_UP_POOL_ENDPOINT,
            "down": LIMIT_DOWN_POOL_ENDPOINT,
            "break": LIMIT_BREAK_POOL_ENDPOINT,
        }
        key = kind.strip().lower()
        if key not in mapping:
            raise ValueError("kind must be one of up/down/break")
        return self._get(mapping[key], {})

    def security_events(self, ticker: str, *, date: Optional[str] = None) -> HiThinkSecurityEventBundle:
        code = ticker.strip().upper()
        if not code or "." not in code:
            raise ValueError("ticker must include exchange suffix")
        anomaly = self.anomaly_for_stocks([code])
        dragon = self.dragon_tiger(board_type="all", date=date)
        return HiThinkSecurityEventBundle(ticker=code, anomaly=anomaly, dragon_tiger=dragon)
