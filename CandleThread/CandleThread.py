import time
from enum import Enum
import ccxt
from datetime import datetime
from PyQt6.QtCore import QThread, pyqtSignal


class CandleType(Enum):
    ERROR=-1
    NONE=0
    UP=1
    BLUE=2
    GREEN=3
    DOWN= 4
    VIOLET=5
    RED=6

class Candle:
    def __init__(self, time_stamp:float, open_price:float, high:float, low:float, close_price:float, volume:float):
        self.c_time_stamp = time_stamp
        self.c_open = open_price
        self.c_high = high
        self.c_low = low
        self.c_close = close_price
        self.c_volume = volume
        self.c_type = CandleType.UP
        if close_price < open_price:
            self.c_type = CandleType.DOWN
        self.bodycolor_map = {1:'lightgray',2:'blue', 3:'green', 4:'darkgray', 5:'violet', 6:'red'}


class CandleThread(QThread):
    # Define signals for thread-safe communication with GUI
    candle_received = pyqtSignal(Candle)  # Signal to emit new candle data
    error_occurred = pyqtSignal(str)  # Signal to emit error messages
    status_message = pyqtSignal(str)  # Signal to emit status messages

    def __init__(self, symbol, timeframe):
        """
        Initialize the CandleThread.

        Args:
            symbol (str): Trading pair symbol (e.g., 'BTC/USDT')
            timeframe (str): Timeframe for candles (e.g., '1m', '3m', '5m', '15m', '1h')
        """
        super().__init__()
        self.symbol = symbol
        self.timeframe = timeframe
        self.running = False
        self.exchange = None
        self.last_timestamp = None

        # Convert timeframe to seconds for sleep duration
        self.sleep_duration = self._timeframe_to_seconds(timeframe)

    def _timeframe_to_seconds(self, timeframe):
        """Convert timeframe string to seconds."""
        unit = timeframe[-1]
        value = int(timeframe[:-1])

        multipliers = {
            'm': 60,  # minutes
            'h': 3600,  # hours
            'd': 86400,  # days
            'w': 604800  # weeks
        }

        return value * multipliers.get(unit, 60)

    def run(self):
        """Main thread execution method."""
        self.running = True

        try:
            # Initialize Binance exchange
            self.exchange = ccxt.binance({
                'enableRateLimit': True
            })

            self.status_message.emit(f"Started fetching {self.symbol} {self.timeframe} candles from Binance")

        except Exception as e:
            error_msg = f"Error initializing Binance exchange: {str(e)}"
            self.error_occurred.emit(error_msg)
            self.running = False
            return

        while self.running:
            try:
                new_candle = None
                # Fetch OHLCV data
                ohlcv = self.exchange.fetch_ohlcv(
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    limit=1  # Get only the latest completed candle
                )

                if ohlcv and len(ohlcv) > 0:
                    # Get the most recent candle
                    candle_data = ohlcv[-1]
                    timestamp = candle_data[0]

                    print(candle_data)

                    # Only process if this is a new candle (avoid duplicates)
                    if timestamp != self.last_timestamp:
                        self.last_timestamp = timestamp

                        # Parse OHLCV data
                        # Format: [timestamp, open, high, low, close, volume]
                        target_candle = ohlcv[-1]  # -1 for last, -2 for second-to-last, etc.
                        timestamp = datetime.fromtimestamp(target_candle[0] / 1000.0)
                        timestamp_f = timestamp.timestamp()
                        open_price = target_candle[1]
                        high_price = target_candle[2]
                        low_price = target_candle[3]
                        close_price = target_candle[4]
                        volume = target_candle[5]
                        new_candle = Candle(timestamp_f, open_price, high_price, low_price, close_price, volume)

                        """
                        candle = Candle(
                            c_time_stamp=datetime.fromtimestamp(timestamp / 1000),
                            c_open=float(candle_data[1]),
                            c_high=float(candle_data[2]),
                            c_low=float(candle_data[3]),
                            c_close=float(candle_data[4]),
                            c_volume=float(candle_data[5]),
                            c_type=self._determine_candle_type(
                                float(candle_data[1]),
                                float(candle_data[4])
                            )
                        )
                        """

                        # Emit signal with candle data (thread-safe)
                        self.candle_received.emit(new_candle)

                        # Log successful fetch
                        time_str = datetime.fromtimestamp(new_candle.c_time_stamp).strftime('%Y-%m-%d %H:%M:%S')
                        status_msg = (
                            f"Fetched candle: {time_str} O:{new_candle.c_open:.2f} "
                            f"H:{new_candle.c_high:.2f} L:{new_candle.c_low:.2f} C:{new_candle.c_close:.2f}"
                        )
                        self.status_message.emit(status_msg)

            except ccxt.NetworkError as e:
                error_msg = f"Network error: {str(e)}"
                self.error_occurred.emit(error_msg)

            except ccxt.ExchangeError as e:
                error_msg = f"Exchange error: {str(e)}"
                self.error_occurred.emit(error_msg)

            except Exception as e:
                error_msg = f"Unexpected error: {str(e)}"
                self.error_occurred.emit(error_msg)

            # Sleep for the timeframe duration before fetching next candle
            # this will check every 10 seconds for a new state of self.running
            # for better user responsiveness
            sleep_cnt = 0
            while self.running and sleep_cnt < self.sleep_duration/10:
                time.sleep(10)
                sleep_cnt += 1

    def _determine_candle_type(self, open_price, close_price):
        """Determine candle type based on open and close prices."""
        if close_price > open_price:
            return CandleType(2)  # Bullish - blue
        elif close_price < open_price:
            return CandleType(6)  # Bearish - red
        else:
            return CandleType(1)  # Doji - lightgray

    def stop(self):
        """Stop the thread gracefully."""
        self.running = False
        self.status_message.emit(f"Stopped fetching {self.symbol} {self.timeframe} candles")