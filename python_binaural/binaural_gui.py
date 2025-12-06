import sys
import numpy as np
from pathlib import Path
import soundfile as sf
import sounddevice as sd
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QPushButton,
                             QLabel, QFileDialog)
from PyQt6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QBrush
from PyQt6.QtCore import Qt, QPoint, QRect



class WaveformCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.waveform_pixmap = None
        self.setStyleSheet("background-color: white; border: 1px solid #ccc;")

    def draw_waveform(self, audio_data):
        # Handle stereo by converting to mono
        if len(audio_data.shape) > 1:
            audio_data = np.mean(audio_data, axis=1)

        # Normalize audio data
        if np.max(np.abs(audio_data)) > 0:
            audio_data = audio_data / np.max(np.abs(audio_data))

        # Downsample for display (take every nth sample)
        downsample_factor = max(1, len(audio_data) // self.width())
        downsampled = audio_data[::downsample_factor]

        # Create pixmap
        width = self.width()
        height = self.height()
        pixmap = QPixmap(width, height)
        pixmap.fill(Qt.GlobalColor.white)

        # Draw waveform
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(0, 100, 200), 1)
        painter.setPen(pen)

        # Draw center line
        center_y = height // 2
        painter.drawLine(0, center_y, width, center_y)

        # Draw waveform
        pen.setColor(QColor(0, 120, 255))
        painter.setPen(pen)

        x_step = width / len(downsampled)
        for i in range(len(downsampled) - 1):
            x1 = i * x_step
            y1 = center_y - downsampled[i] * (height / 2 - 5)
            x2 = (i + 1) * x_step
            y2 = center_y - downsampled[i + 1] * (height / 2 - 5)
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        painter.end()

        self.waveform_pixmap = pixmap
        self.update()

    def paintEvent(self, event):
        if self.waveform_pixmap:
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self.waveform_pixmap)


class WavVisualizer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.wav_data = None
        self.sample_rate = None

    def initUI(self):
        self.setWindowTitle('WAV File Visualizer')
        self.setGeometry(100, 100, 1200, 700)

        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Load button - top left
        self.load_btn = QPushButton('Load', central_widget)
        self.load_btn.setGeometry(10, 10, 80, 40)
        self.load_btn.clicked.connect(self.load_wav_file)

        # Label for filename - next to load button
        self.filename_label = QLabel('No file loaded', central_widget)
        self.filename_label.setGeometry(100, 10, 300, 40)
        self.filename_label.setStyleSheet("color: #333; font-size: 12px; padding: 8px;")

        # Canvas for waveform - right of label
        self.canvas = WaveformCanvas(central_widget)
        self.canvas.setGeometry(410, 10, 750, 200)

        # Play button - right of waveform canvas
        self.play_btn = QPushButton('Play', central_widget)
        self.play_btn.setGeometry(1170, 10, 80, 40)
        self.play_btn.clicked.connect(self.play_wav_file)


        # Click canvas (square) - bottom
        self.click_canvas = ClickCanvas(central_widget)
        self.click_canvas.setGeometry(10, 220, 450, 450)

        # Transform button - below click canvas
        self.transform_btn = QPushButton('Transform', central_widget)
        self.transform_btn.setGeometry(1170, 60, 80, 40)
        self.transform_btn.clicked.connect(self.transform_wav_file)

    def load_wav_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select WAV File", "", "WAV Files (*.wav)"
        )

        if file_path:
            try:
                # Load audio file
                self.wav_data, self.sample_rate = sf.read(file_path)

                # Update label with filename only
                filename = Path(file_path).name
                self.filename_label.setText(f'Loaded: {filename}')

                # Draw waveform
                self.canvas.draw_waveform(self.wav_data)
            except Exception as e:
                self.filename_label.setText(f'Error: {str(e)}')

    def play_wav_file(self):
        if self.wav_data is not None and self.sample_rate is not None:
            try:
                sd.play(self.wav_data, self.sample_rate)
                sd.wait()
            except Exception as e:
                self.filename_label.setText(f'Playback Error: {str(e)}')
        else:
            self.filename_label.setText('No file loaded to play')

    def transform_wav_file(self):
        if self.wav_data is None or self.click_canvas.last_click_pos is None:
            self.filename_label.setText('Load a file and place green dot first')
            return

        try:
            # Get angle and distance from click canvas
            pos = self.click_canvas.last_click_pos
            center = QPoint(self.click_canvas.width() // 2, self.click_canvas.height() // 2)

            dx = pos.x() - center.x()
            dy = pos.y() - center.y()
            distance = np.sqrt(dx ** 2 + dy ** 2)
            angle_rad = np.arctan2(dx, -dy)

            # Handle mono audio
            if len(self.wav_data.shape) == 1:
                mono_data = self.wav_data
            else:
                mono_data = np.mean(self.wav_data, axis=1)

            # Create stereo with ITD (Interaural Time Difference) and ILD (Interaural Level Difference)
            # ITD: phase shift based on angle
            # ILD: amplitude difference based on angle

            # ITD effect: introduce phase shift proportional to angle
            itd_samples = int(np.sin(angle_rad) * 100)  # Max 100 samples delay

            # ILD effect: amplitude scaling based on angle
            left_gain = np.cos(angle_rad / 2) * 0.5 + 0.5
            right_gain = -np.cos(angle_rad / 2) * 0.5 + 0.5

            # Create stereo channels
            left_channel = mono_data.copy()
            right_channel = mono_data.copy()

            # Apply ITD by shifting one channel
            if itd_samples > 0:
                right_channel = np.pad(right_channel, (itd_samples, 0), mode='constant')[:-itd_samples]
            elif itd_samples < 0:
                left_channel = np.pad(left_channel, (-itd_samples, 0), mode='constant')[:-itd_samples]

            # Apply ILD (level difference)
            left_channel = left_channel * left_gain
            right_channel = right_channel * right_gain

            # Combine into stereo
            self.wav_data = np.column_stack((left_channel, right_channel))

            self.filename_label.setText('WAV transformed to stereo with spatial audio')
            self.canvas.draw_waveform(self.wav_data[:, 0])  # Display left channel

        except Exception as e:
            self.filename_label.setText(f'Transform Error: {str(e)}')



class ClickCanvas(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_click_pos = None
        self.setStyleSheet("background-color: white; border: 2px solid black;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw blue circle in the center
        center = QPoint(self.width() // 2, self.height() // 2)
        radius = 8

        painter.setBrush(QBrush(QColor(0, 100, 255)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, radius, radius)

        # Draw green circle at last click position
        if self.last_click_pos:
            painter.setBrush(QBrush(QColor(0, 255, 0)))
            painter.drawEllipse(self.last_click_pos, 10, 10)

        painter.end()

    def mousePressEvent(self, event):
        pos = event.pos()
        print(f"Cursor position: x={pos.x()}, y={pos.y()}")

        # Calculate angle and distance to blue dot center
        center = QPoint(self.width() // 2, self.height() // 2)

        # Distance
        dx = pos.x() - center.x()
        dy = pos.y() - center.y()
        distance = np.sqrt(dx ** 2 + dy ** 2)

        # Angle to vertical line (as fraction of 2*pi, 0 is straight up)
        angle_rad = np.arctan2(dx, -dy)
        angle_fraction = angle_rad / (2 * np.pi)

        print(f"Distance to blue dot: {distance:.2f} px")
        print(f"Angle to vertical line: {angle_fraction:.4f} * 2π")

        # Update last click position and redraw
        self.last_click_pos = pos
        self.update()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    visualizer = WavVisualizer()
    visualizer.show()
    sys.exit(app.exec())