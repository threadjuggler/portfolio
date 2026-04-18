"""
bitunix_api — Bitunix Futures REST API client package.

Quick start
-----------
    from bitunix_api import BitunixClient

    client = BitunixClient(api_key="YOUR_KEY", secret_key="YOUR_SECRET")
    account = client.get_account()
    client.place_order("BTCUSDT", "BUY", "OPEN", "0.001")
"""

from .client import BitunixClient, BASE_URL

__all__ = ["BitunixClient", "BASE_URL"]
