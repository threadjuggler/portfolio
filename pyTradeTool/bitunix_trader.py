"""
Bitunix Futures Multi-Pair Trader — GUI entry point.
API logic lives in the bitunix_api package.
"""

import sys
import time
import json
import pathlib

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QLineEdit, QPushButton, QSlider, QGroupBox,
    QTextEdit, QComboBox, QFrame, QScrollArea,
    QDoubleSpinBox, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QColor, QPalette

from bitunix_api import BitunixClient


VERSION          = "0.01"
DEFAULT_PAIRS    = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
CREDENTIALS_FILE = pathlib.Path(__file__).parent / "bitunix_keys.json"
MAX_ALLOC_PCT    = 60.0   # hard cap: total allocation across all pairs ≤ 60 % of balance


# ---------------------------------------------------------------------------
# Worker thread for async API calls
# ---------------------------------------------------------------------------

class ApiWorker(QThread):
    result = pyqtSignal(str, object)
    error  = pyqtSignal(str, str)

    def __init__(self, tag: str, fn, *args, **kwargs):
        super().__init__()
        self.tag = tag
        self.fn  = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            data = self.fn(*self.args, **self.kwargs)
            self.result.emit(self.tag, data)
        except Exception as exc:
            self.error.emit(self.tag, str(exc))


# ---------------------------------------------------------------------------
# Per-pair widget
# ---------------------------------------------------------------------------

class PairRow(QGroupBox):
    def __init__(self, symbol: str, parent=None):
        super().__init__(symbol, parent)
        self.symbol        = symbol
        self._cached_asset = 0.0   # updated by BitunixTrader whenever the balance changes
        self._build_ui()

    def _build_ui(self):
        layout = QGridLayout()
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setHorizontalSpacing(10)

        # Side
        self.side_combo = QComboBox()
        self.side_combo.addItems(["BUY (Long)", "SELL (Short)"])
        self.side_combo.setFixedWidth(120)

        # Trade side
        self.trade_side_combo = QComboBox()
        self.trade_side_combo.addItems(["OPEN", "CLOSE"])
        self.trade_side_combo.setFixedWidth(80)

        # Percentage input
        self.pct_spin = QDoubleSpinBox()
        self.pct_spin.setRange(0.0, MAX_ALLOC_PCT)
        self.pct_spin.setDecimals(1)
        self.pct_spin.setSingleStep(1.0)
        self.pct_spin.setSuffix(" %")
        self.pct_spin.setFixedWidth(80)
        self.pct_spin.setToolTip(f"Percentage of balance for this pair (total capped at {MAX_ALLOC_PCT:.0f}%)")
        self.pct_spin.valueChanged.connect(self._on_pct_changed)

        # USDT display
        self.usdt_label = QLabel("0.00 USDT")
        self.usdt_label.setFixedWidth(115)
        self.usdt_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # Qty override
        self.qty_spin = QDoubleSpinBox()
        self.qty_spin.setDecimals(6)
        self.qty_spin.setRange(0, 1_000_000)
        self.qty_spin.setSingleStep(0.001)
        self.qty_spin.setFixedWidth(105)
        self.qty_spin.setToolTip("Qty in base coin (0 = derive from % field)")
        self.qty_spin.setPrefix("Qty ")

        # Stop-loss %
        self.sl_spin = QDoubleSpinBox()
        self.sl_spin.setDecimals(1)
        self.sl_spin.setRange(0, 50)
        self.sl_spin.setSingleStep(0.5)
        self.sl_spin.setValue(2.0)
        self.sl_spin.setFixedWidth(90)
        self.sl_spin.setSuffix(" % SL")
        self.sl_spin.setToolTip("Stop-loss distance from entry price (0 = no SL)")

        # Leverage spinbox
        from PyQt6.QtWidgets import QSpinBox
        self.lev_spin = QSpinBox()
        self.lev_spin.setRange(1, 125)
        self.lev_spin.setValue(10)
        self.lev_spin.setFixedWidth(68)
        self.lev_spin.setPrefix("x")
        self.lev_spin.setToolTip("Leverage (1–125). Click Set Lev to apply.")

        # Set leverage button
        self.lev_btn = QPushButton("Set Lev")
        self.lev_btn.setFixedWidth(62)
        self.lev_btn.setStyleSheet("background-color: #37474f; color: white;")

        # Place button
        self.place_btn = QPushButton("Place")
        self.place_btn.setFixedWidth(60)
        self.place_btn.setStyleSheet("background-color: #2e7d32; color: white;")

        # Status
        self.status_label = QLabel("")
        self.status_label.setFixedWidth(200)

        col = 0
        layout.addWidget(self.side_combo,        0, col); col += 1
        layout.addWidget(self.trade_side_combo,  0, col); col += 1
        layout.addWidget(self.pct_spin,          0, col); col += 1
        layout.addWidget(self.usdt_label,        0, col); col += 1
        layout.addWidget(self.qty_spin,          0, col); col += 1
        layout.addWidget(self.sl_spin,           0, col); col += 1
        layout.addWidget(self.lev_spin,          0, col); col += 1
        layout.addWidget(self.lev_btn,           0, col); col += 1
        layout.addWidget(self.place_btn,         0, col); col += 1
        layout.addWidget(self.status_label,      0, col)

        self.setLayout(layout)

    def set_asset(self, asset: float):
        """Called by BitunixTrader whenever the reference asset amount changes."""
        self._cached_asset = asset
        self._refresh_usdt()

    def _on_pct_changed(self, _):
        self._refresh_usdt()

    def _refresh_usdt(self):
        amount = self._cached_asset * self.pct_spin.value() / 100.0
        self.usdt_label.setText(f"{amount:,.2f} USDT")

    def update_usdt(self, asset: float):
        self.set_asset(asset)

    def get_side(self) -> str:
        return "BUY" if self.side_combo.currentIndex() == 0 else "SELL"

    def get_trade_side(self) -> str:
        return self.trade_side_combo.currentText()

    def get_pct(self) -> float:
        return self.pct_spin.value() / 100.0

    def get_sl_pct(self) -> float:
        return self.sl_spin.value()

    def get_leverage(self) -> int:
        return self.lev_spin.value()

    def set_leverage_display(self, value: int):
        self.lev_spin.setValue(max(1, min(125, value)))

    def set_status(self, msg: str, ok: bool = True):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet(f"color: {'#66bb6a' if ok else '#ef9a9a'};")

    def get_settings(self) -> dict:
        return {
            "symbol":    self.symbol,
            "side_idx":  self.side_combo.currentIndex(),
            "trade_idx": self.trade_side_combo.currentIndex(),
            "pct":       self.pct_spin.value(),
            "qty":       self.qty_spin.value(),
            "sl_pct":    self.sl_spin.value(),
            "leverage":  self.lev_spin.value(),
        }

    def apply_settings(self, data: dict):
        self.side_combo.setCurrentIndex(data.get("side_idx", 0))
        self.trade_side_combo.setCurrentIndex(data.get("trade_idx", 0))
        self.pct_spin.setValue(data.get("pct", data.get("slider_pct", 0)))  # slider_pct for back-compat
        self.qty_spin.setValue(data.get("qty", 0.0))
        self.sl_spin.setValue(data.get("sl_pct", 2.0))
        self.lev_spin.setValue(data.get("leverage", 10))


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class BitunixTrader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Bitunix Futures Trader v{VERSION}")
        self.setMinimumSize(1180, 700)
        self.client: BitunixClient | None = None
        self.available_balance: float = 0.0
        self.pair_rows: list[PairRow] = []
        self._workers: list[ApiWorker] = []
        self._build_ui()
        self._load_credentials()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        root.addWidget(self._cred_group())
        root.addWidget(self._account_bar())
        root.addWidget(self._pairs_group())
        root.addWidget(self._bulk_bar())
        root.addWidget(self._log_box())

    def _cred_group(self) -> QGroupBox:
        grp = QGroupBox("API Credentials")
        layout = QHBoxLayout()

        layout.addWidget(QLabel("API Key:"))
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setPlaceholderText("Paste your API key here")
        self.api_key_edit.setMinimumWidth(260)
        layout.addWidget(self.api_key_edit)

        layout.addWidget(QLabel("Secret Key:"))
        self.secret_edit = QLineEdit()
        self.secret_edit.setPlaceholderText("Paste your secret key here")
        self.secret_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret_edit.setMinimumWidth(260)
        layout.addWidget(self.secret_edit)

        self.store_btn = QPushButton("Store Keys")
        self.store_btn.setFixedWidth(88)
        self.store_btn.setToolTip(f"Save credentials to {CREDENTIALS_FILE}")
        self.store_btn.clicked.connect(self._save_credentials)
        layout.addWidget(self.store_btn)

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setFixedWidth(90)
        self.connect_btn.setStyleSheet(
            "background-color: #1565c0; color: white; font-weight: bold;"
        )
        self.connect_btn.clicked.connect(self._on_connect)
        layout.addWidget(self.connect_btn)

        layout.addStretch()
        grp.setLayout(layout)
        return grp

    def _account_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Available Balance:"))
        self.balance_label = QLabel("—")
        self.balance_label.setFont(QFont("Monospace", 11, QFont.Weight.Bold))
        layout.addWidget(self.balance_label)

        layout.addSpacing(20)
        layout.addWidget(QLabel("Asset USDT override:"))
        self.total_spin = QDoubleSpinBox()
        self.total_spin.setRange(0, 10_000_000)
        self.total_spin.setDecimals(2)
        self.total_spin.setSingleStep(100)
        self.total_spin.setFixedWidth(135)
        self.total_spin.setToolTip(
            "Override the asset amount for % calculations (0 = use fetched balance)"
        )
        self.total_spin.valueChanged.connect(self._refresh_usdt_labels)
        layout.addWidget(self.total_spin)

        layout.addSpacing(20)
        layout.addWidget(QLabel("Allocated:"))
        self.alloc_label = QLabel("0.0 % / 60 %  —  0.00 USDT")
        self.alloc_label.setFont(QFont("Monospace", 10))
        layout.addWidget(self.alloc_label)

        self.refresh_btn = QPushButton("Refresh Balance")
        self.refresh_btn.setFixedWidth(120)
        self.refresh_btn.clicked.connect(self._on_refresh_balance)
        layout.addWidget(self.refresh_btn)

        layout.addStretch()
        return bar

    def _pairs_group(self) -> QGroupBox:
        grp = QGroupBox("Trading Pairs")
        outer = QVBoxLayout(grp)

        ctrl = QHBoxLayout()
        self.new_pair_edit = QLineEdit()
        self.new_pair_edit.setPlaceholderText("e.g. DOGEUSDT")
        self.new_pair_edit.setFixedWidth(120)
        self.new_pair_edit.returnPressed.connect(self._on_add_pair)
        add_btn = QPushButton("Add Pair")
        add_btn.setFixedWidth(80)
        add_btn.clicked.connect(self._on_add_pair)
        remove_btn = QPushButton("Remove Last")
        remove_btn.setFixedWidth(100)
        remove_btn.clicked.connect(self._on_remove_pair)
        ctrl.addWidget(QLabel("Add pair:"))
        ctrl.addWidget(self.new_pair_edit)
        ctrl.addWidget(add_btn)
        ctrl.addWidget(remove_btn)
        ctrl.addStretch()
        outer.addLayout(ctrl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._pairs_container = QWidget()
        self._pairs_layout = QVBoxLayout(self._pairs_container)
        self._pairs_layout.setSpacing(4)
        self._pairs_layout.addStretch()
        scroll.setWidget(self._pairs_container)
        outer.addWidget(scroll)

        for sym in DEFAULT_PAIRS:
            self._add_pair_row(sym)

        return grp

    def _bulk_bar(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        def _btn(label: str, color: str, slot) -> QPushButton:
            b = QPushButton(label)
            b.setFixedHeight(36)
            b.setStyleSheet(
                f"background-color: {color}; color: white; font-weight: bold; font-size: 13px;"
            )
            b.clicked.connect(slot)
            return b

        layout.addWidget(_btn("All LONG",            "#1565c0", self._on_place_all_long))
        layout.addWidget(_btn("All SHORT",           "#6a1b9a", self._on_place_all_short))
        layout.addWidget(_btn("Place ALL (as set)",  "#2e7d32", self._on_place_all))
        layout.addWidget(_btn("Close ALL Positions", "#b71c1c", self._on_close_all_positions))
        layout.addStretch()
        return bar

    def _log_box(self) -> QGroupBox:
        grp = QGroupBox("Log")
        layout = QVBoxLayout(grp)
        grp.setMaximumHeight(160)
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setFont(QFont("Monospace", 9))
        layout.addWidget(self.log_edit)
        return grp

    # ------------------------------------------------------------------
    # Pair management
    # ------------------------------------------------------------------

    def _add_pair_row(self, symbol: str):
        symbol = symbol.upper().strip()
        if not symbol:
            return
        if symbol in [r.symbol for r in self.pair_rows]:
            self._log(f"{symbol} already listed.")
            return
        row = PairRow(symbol)
        row.pct_spin.valueChanged.connect(lambda _, r=row: self._on_alloc_changed(r))
        row.place_btn.clicked.connect(lambda _, r=row: self._place_single_with_sl(r))
        row.lev_btn.clicked.connect(lambda _, r=row: self._set_leverage(r))
        self.pair_rows.append(row)
        self._pairs_layout.insertWidget(self._pairs_layout.count() - 1, row)
        if self.client:
            self._fetch_leverage(row)

    def _on_add_pair(self):
        self._add_pair_row(self.new_pair_edit.text())
        self.new_pair_edit.clear()

    def _on_remove_pair(self):
        if not self.pair_rows:
            return
        row = self.pair_rows.pop()
        self._pairs_layout.removeWidget(row)
        row.deleteLater()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_asset(self) -> float:
        v = self.total_spin.value()
        return v if v > 0 else self.available_balance

    def _require_client(self) -> bool:
        if self.client is None:
            QMessageBox.warning(self, "Not Connected", "Enter API credentials and click Connect.")
            return False
        return True

    def _log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self.log_edit.append(f"[{ts}] {msg}")

    def _refresh_usdt_labels(self):
        asset = self._get_asset()
        for row in self.pair_rows:
            row.set_asset(asset)
        self._update_alloc_label()

    def _on_alloc_changed(self, changed_row: "PairRow"):
        """Enforce MAX_ALLOC_PCT cap across all pairs, then refresh totals."""
        total = sum(r.pct_spin.value() for r in self.pair_rows)
        if total > MAX_ALLOC_PCT:
            excess = total - MAX_ALLOC_PCT
            new_val = max(0.0, changed_row.pct_spin.value() - excess)
            changed_row.pct_spin.blockSignals(True)
            changed_row.pct_spin.setValue(new_val)
            changed_row.pct_spin.blockSignals(False)
            changed_row._refresh_usdt()
        self._update_alloc_label()

    def _update_alloc_label(self):
        total_pct  = sum(r.pct_spin.value() for r in self.pair_rows)
        asset      = self._get_asset()
        total_usdt = asset * total_pct / 100.0
        color = "#ef9a9a" if total_pct > MAX_ALLOC_PCT else "#66bb6a"
        self.alloc_label.setText(
            f"{total_pct:.1f} % / {MAX_ALLOC_PCT:.0f} %  —  {total_usdt:,.2f} USDT"
        )
        self.alloc_label.setStyleSheet(f"color: {color};")

    def _spawn(self, tag: str, fn, *args, on_result=None, **kwargs) -> ApiWorker:
        worker = ApiWorker(tag, fn, *args, **kwargs)
        if on_result:
            worker.result.connect(on_result)
        worker.error.connect(lambda t, e: self._log(f"ERROR [{t}]: {e}"))
        self._workers.append(worker)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.start()
        return worker

    def _cleanup_worker(self, worker: ApiWorker):
        if worker in self._workers:
            self._workers.remove(worker)

    # ------------------------------------------------------------------
    # Credential persistence
    # ------------------------------------------------------------------

    def _load_credentials(self):
        if not CREDENTIALS_FILE.exists():
            return
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            self.api_key_edit.setText(data.get("api_key", ""))
            self.secret_edit.setText(data.get("secret_key", ""))
            if (override := data.get("asset_override", 0.0)) > 0:
                self.total_spin.setValue(override)
            saved_pairs = data.get("pairs", [])
            if saved_pairs:
                self._restore_pairs(saved_pairs)
        except Exception as exc:
            self._log(f"Could not load settings: {exc}")

    def _restore_pairs(self, pairs: list[dict]):
        # Remove current rows
        for row in list(self.pair_rows):
            self._pairs_layout.removeWidget(row)
            row.deleteLater()
        self.pair_rows.clear()
        # Recreate from saved settings
        for p in pairs:
            sym = p.get("symbol", "").upper().strip()
            if not sym:
                continue
            self._add_pair_row(sym)
            self.pair_rows[-1].apply_settings(p)

    def _save_credentials(self):
        key    = self.api_key_edit.text().strip()
        secret = self.secret_edit.text().strip()
        if not key and not secret:
            QMessageBox.warning(self, "Nothing to save", "Both fields are empty.")
            return
        try:
            payload = {
                "api_key":        key,
                "secret_key":     secret,
                "asset_override": self.total_spin.value(),
                "pairs":          [r.get_settings() for r in self.pair_rows],
            }
            CREDENTIALS_FILE.write_text(json.dumps(payload, indent=2))
            self._log(f"Settings saved to {CREDENTIALS_FILE}.")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    # ------------------------------------------------------------------
    # Connect
    # ------------------------------------------------------------------

    def _on_connect(self):
        key    = self.api_key_edit.text().strip()
        secret = self.secret_edit.text().strip()
        if not key or not secret:
            QMessageBox.warning(self, "Missing Credentials", "Enter both API key and Secret key.")
            return
        self.client = BitunixClient(key, secret)
        self.connect_btn.setText("Connected ✓")
        self.connect_btn.setStyleSheet("background-color: #2e7d32; color: white; font-weight: bold;")
        self._log("Client initialised — fetching balance and leverage…")
        self._on_refresh_balance()
        for row in self.pair_rows:
            self._fetch_leverage(row)

    # ------------------------------------------------------------------
    # Balance
    # ------------------------------------------------------------------

    def _on_refresh_balance(self):
        if not self._require_client():
            return
        self._spawn("balance", self.client.get_account, on_result=self._on_balance_result)

    def _on_balance_result(self, _tag: str, data: dict):
        if data.get("code") != 0:
            self._log(f"Balance error (code {data.get('code')}): {data.get('msg', data)}")
            return
        raw = data.get("data", {})
        # API may return a single dict or a list — normalise to dict
        if isinstance(raw, list):
            info = next(
                (x for x in raw if x.get("marginCoin", "").upper() == "USDT"),
                raw[0] if raw else {},
            )
        else:
            info = raw
        avail = float(info.get("available", 0))
        self.available_balance = avail
        self.balance_label.setText(f"{avail:,.2f} USDT")
        if self.total_spin.value() == 0:
            self.total_spin.setValue(avail)
        self._refresh_usdt_labels()
        self._log(
            f"Balance — available: {avail:,.2f} USDT | "
            f"margin: {info.get('margin','?')} | "
            f"unrealised PNL: {info.get('crossUnrealizedPNL','?')}"
        )

    # ------------------------------------------------------------------
    # Placing orders
    # ------------------------------------------------------------------

    def _place_single_with_sl(self, row: PairRow, force_side: str | None = None):
        if not self._require_client():
            return
        if row.qty_spin.value() == 0 and row.get_pct() == 0:
            self._log(f"[{row.symbol}] Set a % or a Qty override before placing.")
            return
        side       = force_side if force_side else row.get_side()
        trade_side = row.get_trade_side()
        # Always fetch the ticker: needed to convert % → base-coin qty and/or compute SL price.
        self._spawn(
            f"ticker_{row.symbol}",
            self.client.get_tickers,
            [row.symbol],
            on_result=lambda _, d, r=row, s=side, ts=trade_side: (
                self._do_place(r, s, ts, d)
            ),
        )

    def _do_place(self, row: PairRow, side: str, trade_side: str, ticker_data: dict):
        """Resolve qty and SL from ticker data, then fire the order."""
        # --- extract last price ---
        last_price: float = 0.0
        if ticker_data.get("code") == 0:
            tickers = ticker_data.get("data", [])
            entry   = (
                next((t for t in tickers if t.get("symbol") == row.symbol), None)
                if isinstance(tickers, list)
                else (tickers if tickers.get("symbol") == row.symbol else None)
            )
            if entry:
                last_price = float(entry.get("lastPrice", 0) or 0)

        if last_price <= 0:
            self._log(f"[{row.symbol}] Could not get last price — order aborted.")
            return

        # --- resolve qty ---
        qty_override = row.qty_spin.value()
        if qty_override > 0:
            qty_str = f"{qty_override:.6f}"
        else:
            usdt     = self._get_asset() * row.get_pct()
            leverage = row.get_leverage()
            qty_val  = (usdt * leverage) / last_price
            qty_str  = f"{qty_val:.6f}"
            base     = row.symbol.replace("USDT", "").replace("usdt", "")
            self._log(
                f"[{row.symbol}] {usdt:.2f} USDT × x{leverage} ÷ {last_price:,.2f}"
                f" = {qty_str} {base} (margin: {usdt:.2f} USDT)"
            )

        # --- resolve SL price ---
        sl_pct       = row.get_sl_pct()
        sl_price_str: str | None = None
        if sl_pct > 0:
            factor       = (1 - sl_pct / 100) if side == "BUY" else (1 + sl_pct / 100)
            sl_price_str = f"{last_price * factor:.4f}"
            self._log(f"[{row.symbol}] SL {sl_pct}% → slPrice={sl_price_str}")

        self._log(
            f"Placing {side} {trade_side} MARKET {row.symbol} "
            f"qty={qty_str} slPrice={sl_price_str}…"
        )
        self._spawn(
            f"place_{row.symbol}",
            self.client.place_order,
            row.symbol, side, trade_side, qty_str, sl_price_str,
            on_result=lambda _, d, r=row: self._on_place_result(_, d, r),
        )

    def _on_place_result(self, _tag: str, data: dict, row: PairRow):
        if data.get("code") == 0:
            oid = data.get("data", {}).get("orderId", "")
            row.set_status(f"OK {oid[:14]}", ok=True)
            self._log(f"[{row.symbol}] Order placed — orderId={oid}")
        else:
            msg = data.get("msg", str(data))
            row.set_status(f"ERR: {msg[:35]}", ok=False)
            self._log(f"[{row.symbol}] Place failed (code {data.get('code')}): {msg}")

    # Bulk place variants
    def _on_place_all(self):
        if not self._require_client():
            return
        for row in self.pair_rows:
            self._place_single_with_sl(row)

    def _on_place_all_long(self):
        if not self._require_client():
            return
        for row in self.pair_rows:
            self._place_single_with_sl(row, force_side="BUY")

    def _on_place_all_short(self):
        if not self._require_client():
            return
        for row in self.pair_rows:
            self._place_single_with_sl(row, force_side="SELL")

    # ------------------------------------------------------------------
    # Leverage
    # ------------------------------------------------------------------

    def _set_leverage(self, row: PairRow):
        if not self._require_client():
            return
        lev = row.get_leverage()
        self._log(f"[{row.symbol}] Setting leverage to x{lev}…")
        self._spawn(
            f"lev_{row.symbol}",
            self.client.set_leverage,
            row.symbol, lev,
            on_result=lambda _, d, r=row: self._on_leverage_result(d, r),
        )

    def _on_leverage_result(self, data: dict, row: PairRow):
        if data.get("code") == 0:
            row.set_status(f"Lev x{row.get_leverage()} set", ok=True)
            self._log(f"[{row.symbol}] Leverage set to x{row.get_leverage()}.")
        else:
            msg = data.get("msg", str(data))
            row.set_status(f"Lev ERR: {msg[:30]}", ok=False)
            self._log(f"[{row.symbol}] Set leverage failed: {msg}")

    def _fetch_leverage(self, row: PairRow):
        """Fetch current leverage from the exchange and populate the spinbox."""
        if not self._require_client():
            return
        self._spawn(
            f"getlev_{row.symbol}",
            self.client.get_leverage,
            row.symbol,
            on_result=lambda _, d, r=row: self._on_fetch_leverage_result(d, r),
        )

    def _on_fetch_leverage_result(self, data: dict, row: PairRow):
        if data.get("code") == 0:
            lev = data.get("data", {}).get("leverage")
            if lev is not None:
                row.set_leverage_display(int(lev))
                self._log(f"[{row.symbol}] Current leverage: x{lev}")
        else:
            self._log(f"[{row.symbol}] Get leverage failed: {data.get('msg', data)}")

    # ------------------------------------------------------------------
    # Close all open positions
    # ------------------------------------------------------------------

    def _on_close_all_positions(self):
        if not self._require_client():
            return
        self._log("Fetching open positions…")
        self._spawn(
            "positions",
            self.client.get_positions,
            on_result=self._on_positions_for_close,
        )

    def _on_positions_for_close(self, _tag: str, data: dict):
        if data.get("code") != 0:
            self._log(f"Positions fetch failed: {data.get('msg', data)}")
            return
        raw = data.get("data", {})
        positions = raw.get("list", raw) if isinstance(raw, dict) else raw
        if not isinstance(positions, list):
            positions = []
        closed = 0
        for pos in positions:
            sym        = pos.get("symbol", "")
            qty        = pos.get("qty", "0")
            side       = pos.get("side", "LONG")
            close_side = "SELL" if side == "LONG" else "BUY"
            self._log(f"Closing {side} {sym} qty={qty} → {close_side} CLOSE MARKET…")
            self._spawn(
                f"close_{sym}_{closed}",
                self.client.place_order,
                sym, close_side, "CLOSE", qty, None,
                on_result=lambda _, d, s=sym: self._log(
                    f"[{s}] Close {'OK' if d.get('code')==0 else 'FAILED'}: {d.get('msg','')}"
                ),
            )
            closed += 1
        if closed == 0:
            self._log("No open positions found.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(28, 28, 28))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Base,            QColor(42, 42, 42))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(52, 52, 52))
    pal.setColor(QPalette.ColorRole.ToolTipBase,     QColor(50, 50, 50))
    pal.setColor(QPalette.ColorRole.ToolTipText,     QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Text,            QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Button,          QColor(52, 52, 52))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.BrightText,      QColor(255, 100, 100))
    pal.setColor(QPalette.ColorRole.Link,            QColor(70, 130, 200))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(42, 130, 218))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(0, 0, 0))
    app.setPalette(pal)

    win = BitunixTrader()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
