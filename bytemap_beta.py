import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                            QProgressBar, QFileDialog, QMessageBox, QFrame,
                            QStatusBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QIcon
from PIL import Image
import os
import zstandard as zstd
import logging

# Configure error logging
logging.basicConfig(filename='error.log', level=logging.ERROR)

class ConversionWorker(QThread):
    progress = pyqtSignal(int)
    finished = pyqtSignal(str, bool)
    error = pyqtSignal(str)

    def __init__(self, mode, input_file, output_dir):
        super().__init__()
        self.mode = mode
        self.input_file = input_file
        self.output_dir = output_dir

    def compress_data(self, data):
        try:
            cctx = zstd.ZstdCompressor()
            return cctx.compress(data)
        except Exception as e:
            logging.error(f"Compression error: {e}")
            raise

    def decompress_data(self, data):
        try:
            dctx = zstd.ZstdDecompressor()
            return dctx.decompress(data)
        except Exception as e:
            logging.error(f"Decompression error: {e}")
            raise

    def binary_to_rgba_pixels(self, binary_data):
        padding_length = (32 - len(binary_data) % 32) % 32
        binary_data += '0' * padding_length
        pixels = []

        for i in range(0, len(binary_data), 32):
            chunk = binary_data[i:i+32]
            r = int(chunk[0:8], 2)
            g = int(chunk[8:16], 2)
            b = int(chunk[16:24], 2)
            a = int(chunk[24:32], 2)
            pixels.append((r, g, b, a))

        return pixels, padding_length

    def rgba_pixels_to_binary(self, pixels):
        binary_data = []
        for pixel in pixels:
            r, g, b, a = pixel
            binary_data.append(f'{r:08b}{g:08b}{b:08b}{a:08b}')
        return ''.join(binary_data)

    def create_image_from_binary(self, binary_data, width, height):
        pixels, _ = self.binary_to_rgba_pixels(binary_data)
        img = Image.new('RGBA', (width, height))
        img.putdata(pixels)
        return img

    def create_binary_from_image(self, img):
        pixels = list(img.getdata())
        return self.rgba_pixels_to_binary(pixels)

    def run(self):
        try:
            if self.mode == 'to_image':
                self.convert_to_image()
            else:
                self.convert_to_file()
        except Exception as e:
            self.error.emit(str(e))

    def convert_to_image(self):
        try:
            self.progress.emit(10)
            
            with open(self.input_file, "rb") as f:
                file_data = f.read()

            original_size = len(file_data)
            self.progress.emit(30)
            
            compressed_data = self.compress_data(file_data)
            compressed_size = len(compressed_data)

            if compressed_size >= original_size:
                self.error.emit("Compressed file is not smaller than the original.")
                return

            binary_data = ''.join(format(byte, '08b') for byte in compressed_data)
            self.progress.emit(60)

            pixel_count = (len(binary_data) + 31) // 32
            width = height = int(pixel_count ** 0.5) + 1

            img = self.create_image_from_binary(binary_data, width, height)

            base_filename = os.path.basename(self.input_file)
            output_filename = os.path.splitext(base_filename)[0] + ".bytemap.png"
            output_file = os.path.join(self.output_dir, output_filename)
            img.save(output_file)

            compression_ratio = compressed_size / original_size
            compression_percentage = (1 - compression_ratio) * 100

            self.progress.emit(100)
            status_message = (f"File converted successfully!\n"
                            f"Original Size: {original_size:,} bytes\n"
                            f"Compressed Size: {compressed_size:,} bytes\n"
                            f"Compression: {compression_percentage:.1f}%\n"
                            f"Saved as: {output_file}")
            self.finished.emit(status_message, True)

        except Exception as e:
            logging.error(f"Error in convert_to_image: {e}")
            self.error.emit(str(e))

    def convert_to_file(self):
        try:
            self.progress.emit(10)
            
            img = Image.open(self.input_file)
            self.progress.emit(30)

            binary_data = self.create_binary_from_image(img)
            self.progress.emit(50)

            byte_data = int(binary_data, 2).to_bytes((len(binary_data) + 7) // 8, byteorder='big')
            self.progress.emit(70)

            decompressed_data = self.decompress_data(byte_data)

            base_filename = os.path.basename(self.input_file)
            output_filename = os.path.splitext(base_filename)[0] + ".output"
            output_file = os.path.join(self.output_dir, output_filename)
            
            with open(output_file, "wb") as f:
                f.write(decompressed_data)

            self.progress.emit(100)
            self.finished.emit(f"Image converted successfully!\nSaved as: {output_file}", True)

        except Exception as e:
            logging.error(f"Error in convert_to_file: {e}")
            self.error.emit(str(e))

class FileSelectionFrame(QFrame):
    def __init__(self, label_text, button_text, file_mode=QFileDialog.FileMode.ExistingFile):
        super().__init__()
        self.file_mode = file_mode
        self.setup_ui(label_text, button_text)

    def setup_ui(self, label_text, button_text):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.label = QLabel(label_text)
        self.label.setMinimumWidth(100)
        self.entry = QLineEdit()
        self.button = QPushButton(button_text)
        self.button.clicked.connect(self.browse)

        layout.addWidget(self.label)
        layout.addWidget(self.entry)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def browse(self):
        if self.file_mode == QFileDialog.FileMode.ExistingFile:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select File")
            if file_path:
                self.entry.setText(file_path)
        else:
            directory = QFileDialog.getExistingDirectory(self, "Select Directory")
            if directory:
                self.entry.setText(directory)

    def get_path(self):
        return self.entry.text()

class ByteMapQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ByteMap - File/Image Converter")
        self.setup_ui()

    def setup_ui(self):
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Add title
        title_label = QLabel("ByteMap Converter")
        title_label.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)

        # Add file selection frames
        self.input_frame = FileSelectionFrame("Input File:", "Browse")
        self.output_frame = FileSelectionFrame("Output Directory:", "Browse", 
                                             QFileDialog.FileMode.Directory)
        
        main_layout.addWidget(self.input_frame)
        main_layout.addWidget(self.output_frame)

        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # Add conversion buttons
        button_layout = QHBoxLayout()
        self.to_image_button = QPushButton("Convert to Image")
        self.to_file_button = QPushButton("Convert to File")
        
        self.to_image_button.clicked.connect(lambda: self.start_conversion('to_image'))
        self.to_file_button.clicked.connect(lambda: self.start_conversion('to_file'))

        button_layout.addWidget(self.to_image_button)
        button_layout.addWidget(self.to_file_button)
        main_layout.addLayout(button_layout)

        # Add status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        # Set window properties
        self.setMinimumWidth(600)
        self.setStyle()

    def setStyle(self):
        # Set style for buttons
        button_style = """
            QPushButton {
                padding: 8px 16px;
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """
        self.to_image_button.setStyleSheet(button_style)
        self.to_file_button.setStyleSheet(button_style)

    def start_conversion(self, mode):
        input_path = self.input_frame.get_path()
        output_dir = self.output_frame.get_path()

        if not input_path or not output_dir:
            QMessageBox.warning(self, "Error", "Please select both input file and output directory.")
            return

        if not os.path.exists(input_path):
            QMessageBox.warning(self, "Error", "Input file does not exist.")
            return

        if not os.path.exists(output_dir):
            QMessageBox.warning(self, "Error", "Output directory does not exist.")
            return

        self.worker = ConversionWorker(mode, input_path, output_dir)
        self.worker.progress.connect(self.update_progress)
        self.worker.finished.connect(self.conversion_finished)
        self.worker.error.connect(self.show_error)
        
        self.toggle_ui(False)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def conversion_finished(self, message, success):
        self.toggle_ui(True)
        if success:
            QMessageBox.information(self, "Success", message)
        self.status_bar.showMessage("Ready")

    def show_error(self, message):
        self.toggle_ui(True)
        QMessageBox.critical(self, "Error", message)
        self.status_bar.showMessage("Error occurred")

    def toggle_ui(self, enabled):
        self.to_image_button.setEnabled(enabled)
        self.to_file_button.setEnabled(enabled)
        self.input_frame.setEnabled(enabled)
        self.output_frame.setEnabled(enabled)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ByteMapQt()
    window.show()
    sys.exit(app.exec())