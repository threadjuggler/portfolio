"""
Bitunix Futures REST API client.

Usage:
    from bitunix_api import BitunixClient

    client = BitunixClient(api_key="...", secret_key="...")
    print(client.get_account())
"""

import hashlib
import json
import secrets
import time

import requests


BASE_URL = "https://fapi.bitunix.com"


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class BitunixClient:
    """Authenticated client for the Bitunix Futures REST API."""

    def __init__(self, api_key: str, secret_key: str):
        self.api_key    = api_key
        self.secret_key = secret_key
        self.session    = requests.Session()

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    def _nonce(self) -> str:
        return secrets.token_hex(16)  # 32 hex chars

    def _sign(self, nonce: str, timestamp: str, query_params: str, body: str) -> str:
        # Bitunix double-SHA256 per docs:
        #   digest = SHA256(nonce + timestamp + apiKey + queryParams + body)
        #   sign   = SHA256(digest + secretKey)
        # queryParams: sorted key+value concatenated WITHOUT any separator
        #   e.g. {id: 1, uid: 200} → "id1uid200"
        digest = _sha256(nonce + timestamp + self.api_key + query_params + body)
        return _sha256(digest + self.secret_key)

    @staticmethod
    def _sign_query(params: dict) -> str:
        """queryParams string for the signature: sorted key+value, no separators."""
        return "".join(f"{k}{v}" for k, v in sorted(params.items()))

    @staticmethod
    def _url_query(params: dict) -> str:
        """Standard URL query string: key=value joined with &."""
        return "&".join(f"{k}={v}" for k, v in sorted(params.items()))

    def _headers(self, nonce: str, timestamp: str, sign: str) -> dict:
        return {
            "api-key":      self.api_key,
            "nonce":        nonce,
            "timestamp":    timestamp,
            "sign":         sign,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # HTTP primitives
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        params     = params or {}
        sign_query = self._sign_query(params)
        url_query  = self._url_query(params)
        nonce      = self._nonce()
        timestamp  = str(int(time.time() * 1000))
        sign       = self._sign(nonce, timestamp, sign_query, "")
        url        = f"{BASE_URL}{path}"
        if url_query:
            url += f"?{url_query}"
        resp = self.session.get(url, headers=self._headers(nonce, timestamp, sign), timeout=10)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        # Compact JSON — do NOT sort keys (use natural insertion order)
        body_str  = json.dumps(body, separators=(",", ":"))
        nonce     = self._nonce()
        timestamp = str(int(time.time() * 1000))
        sign      = self._sign(nonce, timestamp, "", body_str)
        resp = self.session.post(
            f"{BASE_URL}{path}",
            data=body_str,
            headers=self._headers(nonce, timestamp, sign),
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account(self) -> dict:
        """GET /api/v1/futures/account — returns USDT account info."""
        return self._get("/api/v1/futures/account", {"marginCoin": "USDT"})

    def get_leverage(self, symbol: str) -> dict:
        """GET /api/v1/futures/account/get_leverage_margin_mode — current leverage & margin mode."""
        return self._get(
            "/api/v1/futures/account/get_leverage_margin_mode",
            {"symbol": symbol, "marginCoin": "USDT"},
        )

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        """POST /api/v1/futures/account/change_leverage — set leverage for a symbol."""
        return self._post(
            "/api/v1/futures/account/change_leverage",
            {"leverage": leverage, "marginCoin": "USDT", "symbol": symbol},
        )

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------

    def get_tickers(self, symbols: list[str]) -> dict:
        """GET /api/v1/futures/market/tickers — last price, mark price, etc."""
        return self._get(
            "/api/v1/futures/market/tickers",
            {"symbols": ",".join(symbols)},
        )

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------

    def get_positions(self, symbol: str = "") -> dict:
        """GET /api/v1/futures/position/get_pending_positions"""
        params = {}
        if symbol:
            params["symbol"] = symbol
        return self._get("/api/v1/futures/position/get_pending_positions", params)

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def get_pending_orders(self, symbol: str) -> dict:
        """GET /api/v1/futures/trade/get_pending_orders"""
        return self._get("/api/v1/futures/trade/get_pending_orders", {"symbol": symbol})

    def place_order(
        self,
        symbol:     str,
        side:       str,
        trade_side: str,
        qty:        str,
        sl_price:   str | None = None,
    ) -> dict:
        """
        POST /api/v1/futures/trade/place_order — MARKET order.

        Parameters
        ----------
        symbol     : e.g. "BTCUSDT"
        side       : "BUY" | "SELL"
        trade_side : "OPEN" | "CLOSE"
        qty        : quantity in base coin
        sl_price   : absolute stop-loss price (optional)
        """
        body: dict = {
            "orderType": "MARKET",
            "qty":        qty,
            "side":       side,
            "symbol":     symbol,
            "tradeSide":  trade_side,
        }
        if sl_price:
            body["slOrderType"] = "MARKET"
            body["slPrice"]     = sl_price
            body["slStopType"]  = "MARK_PRICE"
        return self._post("/api/v1/futures/trade/place_order", body)

    def cancel_all_orders(self, symbol: str) -> dict:
        """POST /api/v1/futures/trade/cancel_all_orders"""
        return self._post("/api/v1/futures/trade/cancel_all_orders", {"symbol": symbol})

    def cancel_orders(self, symbol: str, order_ids: list[str]) -> dict:
        """POST /api/v1/futures/trade/cancel_orders — cancel specific order IDs."""
        body = {
            "symbol":    symbol,
            "orderList": [{"orderId": oid} for oid in order_ids],
        }
        return self._post("/api/v1/futures/trade/cancel_orders", body)
