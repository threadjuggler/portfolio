import sys
import pandas as pd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QScrollArea,
                             QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QComboBox)
from PyQt6.QtGui import QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QRectF, QPointF

from CandleThread import CandleThread, Candle


class CandlestickWidget(QWidget):
    def __init__(self):
        super().__init__()
        # Initialize empty DataFrame to store candle data
        self.data = pd.DataFrame(columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 'CandleType'])
        self.candle_width = 10
        self.candle_spacing = 2
        self.setMinimumSize(800, 600)
        self.max_candles = 100  # Limit number of displayed candles

    def print_next_candle(self, candle: Candle):
        # Create a new row for the DataFrame
        new_row = {
            'Timestamp': candle.c_time_stamp,
            'Open': candle.c_open,
            'High': candle.c_high,
            'Low': candle.c_low,
            'Close': candle.c_close,
            'Volume': candle.c_volume,
            'CandleType': candle.c_type.value
        }
        # Append the new row
        self.data.loc[len(self.data)] = new_row

        # Limit to max_candles
        if len(self.data) > self.max_candles:
            self.data = self.data.iloc[-self.max_candles:]

        # Trigger repaint
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.data.empty:
            return

        # Find min/max prices for scaling
        min_price = min(self.data['Low'].min(), self.data['Open'].min(), self.data['Close'].min())
        max_price = max(self.data['High'].max(), self.data['Open'].max(), self.data['Close'].max())

        # Calculate price range and scaling
        price_range = max_price - min_price
        height = self.height() - 50  # Leave margin
        width = self.width()
        # Scale factor for price to pixels
        price_scale = height / price_range if price_range > 0 else 1

        price_labels_ruler = []
        my_p_scale = height / 10
        my_step = price_range / 10
        for i in range(10):
            py = int(i * my_p_scale)
            new_p = min_price + my_step * i
            price_labels_ruler.append((new_p, py))

        # draw price labels
        line_color = 'gray'
        pen = QPen(QColor(line_color))
        pen.dashPattern()
        painter.setPen(pen)
        for plabel, pr in price_labels_ruler:
            pr_x = width - 80
            pr_y = int(height - pr)
            # Draw wick
            painter.drawLine(0, pr_y, pr_x, pr_y)
            painter.drawText(QPointF(pr_x + 2, pr_y), f'{plabel:0.2f}')

        # Draw candlesticks
        for i, row in self.data.iterrows():
            x = i * (self.candle_width + self.candle_spacing)

            # Calculate pixel coordinates
            open_y = int(height - (row['Open'] - min_price) * price_scale)
            close_y = int(height - (row['Close'] - min_price) * price_scale)
            high_y = int(height - (row['High'] - min_price) * price_scale)
            low_y = int(height - (row['Low'] - min_price) * price_scale)

            # Set colors
            body_cols = {1: 'lightgray', 2: 'blue', 3: 'green', 4: 'darkgray', 5: 'violet', 6: 'red'}
            body_color = body_cols.get(int(row['CandleType']), 'gray')
            brush = QBrush(QColor(body_color), Qt.BrushStyle.SolidPattern)
            painter.setBrush(brush)
            frame_color = 'green'
            if row['Open'] > row['Close']:
                frame_color = 'red'
            pen = QPen(QColor(frame_color))
            painter.setPen(pen)

            # Draw wick
            painter.drawLine(int(x + self.candle_width / 2), high_y,
                             int(x + self.candle_width / 2), low_y)

            # Draw body
            body_top = min(open_y, close_y)
            body_bottom = max(open_y, close_y)
            painter.drawRect(QRectF(x, body_top,
                                    self.candle_width, body_bottom - body_top))

        # Set widget size
        total_width = int(len(self.data) * (self.candle_width + self.candle_spacing))
        self.setMinimumWidth(max(total_width, 800))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OHLC Candlestick Chart")
        self.is_running = False
        self.max_text_lines = 25
        self.candle_thread = None

        # Available options for trading
        self.available_symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'HBARUSDT']
        self.available_timeframes = ['1m', '3m', '5m', '15m']

        # Create main container widget
        container = QWidget()
        main_layout = QVBoxLayout()

        # Create button layout
        button_layout = QHBoxLayout()
        self.start_stop_button = QPushButton("Start")
        self.start_stop_button.clicked.connect(self.toggle_start_stop)
        button_layout.addWidget(self.start_stop_button)

        self.quit_button = QPushButton("Quit")
        self.quit_button.clicked.connect(self.quit_func)
        button_layout.addWidget(self.quit_button)

        # Add symbol dropdown
        button_layout.addWidget(QLabel("Symbol:"))
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItems(self.available_symbols)
        self.symbol_combo.setCurrentText('BTCUSDT')
        button_layout.addWidget(self.symbol_combo)

        # Add timeframe dropdown
        button_layout.addWidget(QLabel("Timeframe:"))
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(self.available_timeframes)
        self.timeframe_combo.setCurrentText('3m')
        button_layout.addWidget(self.timeframe_combo)

        button_layout.addStretch()  # Push button to the left

        # Create scroll area for candlestick chart
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.candlestick_widget = CandlestickWidget()
        scroll_area.setWidget(self.candlestick_widget)

        # Create text area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        self.text_area.setMinimumHeight(300)  # Half of 600px minimum height

        # Add widgets to main layout
        main_layout.addLayout(button_layout)
        main_layout.addWidget(scroll_area, stretch=1)  # Give scroll area stretch factor
        main_layout.addWidget(self.text_area)

        container.setLayout(main_layout)
        self.setCentralWidget(container)

        # Set window size
        self.setMinimumSize(1600, 1000)

    def toggle_start_stop(self):
        """Toggle button state and start/stop the candle thread"""
        self.is_running = not self.is_running

        if self.is_running:
            self.start_stop_button.setText("Stop")
            self.add_text_line("Button pressed - Starting candle fetching...")

            # Get selected values from dropdowns
            selected_symbol = self.symbol_combo.currentText()
            selected_timeframe = self.timeframe_combo.currentText()

            # Create and start the candle thread
            self.candle_thread = CandleThread(
                symbol=selected_symbol,
                timeframe=selected_timeframe
            )

            # Connect signals to slots (thread-safe communication)
            self.candle_thread.candle_received.connect(self.on_candle_received)
            self.candle_thread.error_occurred.connect(self.on_error_occurred)
            self.candle_thread.status_message.connect(self.add_text_line)

            # Start the thread
            self.candle_thread.start()

        else:
            self.start_stop_button.setText("Start")
            self.add_text_line("Button pressed - Stopping candle fetching...")

            # Stop the candle thread
            if self.candle_thread is not None:
                self.candle_thread.stop()
                self.candle_thread.wait(5000)  # Wait up to 5 seconds for thread to finish
                self.candle_thread = None

    def quit_func(self):
        """ quits the app """
        """Handle window close event - stop thread before closing"""
        self.running = False
        if self.candle_thread is not None and self.candle_thread.isRunning():
            self.candle_thread.stop()
            self.candle_thread.wait(5000)
        sys.exit(0)

    def on_candle_received(self, candle: Candle):
        """Slot to handle candle data received from thread (thread-safe)"""
        self.print_next_candle(candle)

    def on_error_occurred(self, error_message: str):
        """Slot to handle error messages from thread (thread-safe)"""
        self.add_text_line(f"ERROR: {error_message}")

    def add_text_line(self, text):
        """Add a line to the text area and maintain max line limit"""
        # Get current text
        current_text = self.text_area.toPlainText()
        lines = current_text.split('\n') if current_text else []

        # Add new line
        lines.append(text)

        # Keep only the last max_text_lines
        if len(lines) > self.max_text_lines:
            lines = lines[-self.max_text_lines:]

        # Update text area
        self.text_area.setPlainText('\n'.join(lines))

        # Scroll to bottom
        self.text_area.verticalScrollBar().setValue(
            self.text_area.verticalScrollBar().maximum()
        )

    def print_next_candle(self, candle: Candle):
        """Call the widget's print_next_candle method"""
        self.candlestick_widget.print_next_candle(candle)

    def closeEvent(self, event):
        """Handle window close event - stop thread before closing"""
        if self.candle_thread is not None and self.candle_thread.isRunning():
            self.candle_thread.stop()
            self.candle_thread.wait(5000)
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())