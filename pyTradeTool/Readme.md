# pyTradeTool — Bitunix Futures Trader

A PyQt6 desktop GUI for trading perpetual futures on the [Bitunix](https://www.bitunix.com) exchange.
It lets you manage multiple crypto pairs from a single window and execute market orders with one click.

## Features

- **Multi-pair trading** — manage BTC, ETH, SOL, or any other USDT-margined futures pair simultaneously.
- **Bulk actions** — place all orders LONG, all SHORT, or according to individual pair settings with a single button.
- **Close all positions** — fetches every open futures position from the exchange and closes each one at market price.
- **Leverage control** — set and apply per-pair leverage (1–125×) directly from the GUI; current leverage is fetched automatically on connect.
- **% allocation with 60 % hard cap** — enter the percentage of your balance to risk per pair; the total across all pairs is capped at 60 % so margin is always available.
- **Leveraged qty calculation** — quantity sent to the exchange is `(balance × %) × leverage ÷ price`, so the margin used equals your chosen USDT amount while the position is correctly sized for the selected leverage.
- **Stop-loss** — optional per-pair stop-loss in % (default 2 %), converted to an absolute mark-price trigger before the order is placed.
- **Live balance** — fetches available USDT balance on connect with a manual refresh button; supports an override field for paper-trading with a custom amount.
- **Credential & settings persistence** — API key, secret, asset override, and all per-pair settings are saved to `bitunix_keys.json` and reloaded at startup.
- **Dark theme** — Fusion palette with a dark background for comfortable use during trading sessions.

## Project Structure

```
pyTradeTool/
├── bitunix_trader.py       # PyQt6 GUI entry point
├── bitunix_keys.json       # Auto-generated credentials & settings file (git-ignored)
└── bitunix_api/
    ├── __init__.py         # Public package exports
    └── client.py           # Authenticated Bitunix REST API client
```

## Requirements

- Python 3.11+
- `PyQt6`
- `requests`

Install dependencies:

```bash
pip install PyQt6 requests
```

## Usage

```bash
python bitunix_trader.py
```

1. Paste your Bitunix API key and secret, then click **Store Keys** to save them.
2. Click **Connect** to authenticate and fetch your balance and current leverage settings.
3. Set the percentage of balance and leverage for each pair.
4. Click **Place** on an individual pair or use the bulk buttons at the bottom.

## bitunix_api Package

The `bitunix_api` package can be imported independently in other scripts:

```python
from bitunix_api import BitunixClient

client = BitunixClient(api_key="...", secret_key="...")
print(client.get_account())
client.place_order("BTCUSDT", "BUY", "OPEN", "0.001")
```
