import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image
import os
import zstandard as zstd
import logging
import threading

# Configure error logging
logging.basicConfig(filename='error.log', level=logging.ERROR)

def compress_data(data):
    try:
        cctx = zstd.ZstdCompressor()
        compressed_data = cctx.compress(data)
        return compressed_data
    except Exception as e:
        logging.error("Error during compression: %s", e)
        raise

def decompress_data(data):
    try:
        dctx = zstd.ZstdDecompressor()
        decompressed_data = dctx.decompress(data)
        return decompressed_data
    except Exception as e:
        logging.error("Error during decompression: %s", e)
        raise

def binary_to_rgba_pixels(binary_data):
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

def rgba_pixels_to_binary(pixels):
    binary_data = []
    for pixel in pixels:
        r, g, b, a = pixel
        binary_data.append(f'{r:08b}{g:08b}{b:08b}{a:08b}')
    binary_data = ''.join(binary_data)
    return binary_data

def create_image_from_binary(binary_data, width, height):
    pixels, _ = binary_to_rgba_pixels(binary_data)
    img = Image.new('RGBA', (width, height))
    img.putdata(pixels)
    return img

def create_binary_from_image(img):
    pixels = list(img.getdata())
    binary_data = rgba_pixels_to_binary(pixels)
    return binary_data

class ByteMapApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ByteMap - File to Image Conversion")

        self.input_file_label = tk.Label(root, text="Select File:")
        self.input_file_label.grid(row=0, column=0, padx=10, pady=10)

        self.input_file_entry = tk.Entry(root, width=50)
        self.input_file_entry.grid(row=0, column=1, padx=10, pady=10)

        self.input_file_button = tk.Button(root, text="Browse", command=self.select_input_file)
        self.input_file_button.grid(row=0, column=2, padx=10, pady=10)

        self.output_location_label = tk.Label(root, text="Select Save Location:")
        self.output_location_label.grid(row=1, column=0, padx=10, pady=10)

        self.output_location_entry = tk.Entry(root, width=50)
        self.output_location_entry.grid(row=1, column=1, padx=10, pady=10)

        self.output_location_button = tk.Button(root, text="Browse", command=self.select_output_location)
        self.output_location_button.grid(row=1, column=2, padx=10, pady=10)

        self.progress_bar = ttk.Progressbar(root, orient='horizontal', length=400, mode='determinate')
        self.progress_bar.grid(row=2, column=1, padx=10, pady=10)

        self.convert_to_image_button = tk.Button(root, text="Convert File to Image", command=self.start_file_to_image_thread)
        self.convert_to_image_button.grid(row=3, column=1, padx=10, pady=10)

        self.convert_to_file_button = tk.Button(root, text="Convert Image to File", command=self.start_image_to_file_thread)
        self.convert_to_file_button.grid(row=4, column=1, padx=10, pady=10)

        self.status_label = tk.Label(root, text="", fg="green")
        self.status_label.grid(row=5, column=1, padx=10, pady=10)

    def select_input_file(self):
        file_path = filedialog.askopenfilename(title="Select a File")
        if file_path:
            self.input_file_entry.delete(0, tk.END)
            self.input_file_entry.insert(0, file_path)

    def select_output_location(self):
        directory = filedialog.askdirectory(title="Select Output Directory")
        if directory:
            self.output_location_entry.delete(0, tk.END)
            self.output_location_entry.insert(0, directory)

    def update_progress(self, value):
        self.progress_bar['value'] = value
        self.root.update_idletasks()

    def start_file_to_image_thread(self):
        threading.Thread(target=self.convert_file_to_image).start()

    def start_image_to_file_thread(self):
        threading.Thread(target=self.convert_image_to_file).start()

    def convert_file_to_image(self):
        input_file = self.input_file_entry.get()
        output_dir = self.output_location_entry.get()
        if not input_file or not output_dir:
            messagebox.showerror("Error", "Please select a file and output location.")
            return

        try:
            self.update_progress(0)
            
            # Read the original file data
            with open(input_file, "rb") as f:
                file_data = f.read()

            original_size = len(file_data)
            self.update_progress(20)
            
            # Compress the data
            compressed_data = compress_data(file_data)
            compressed_size = len(compressed_data)

            # Check if the compressed data is smaller than the original
            if compressed_size >= original_size:
                messagebox.showinfo("Info", "Compressed file is not smaller than the original. No file saved.")
                return

            # Convert compressed data to binary
            binary_data = ''.join(format(byte, '08b') for byte in compressed_data)

            self.update_progress(50)
            pixel_count = (len(binary_data) + 31) // 32
            width = height = int(pixel_count ** 0.5) + 1

            # Create image from binary data
            img = create_image_from_binary(binary_data, width, height)

            # Save the image
            base_filename = os.path.basename(input_file)
            output_filename = os.path.splitext(base_filename)[0] + ".bytemap.png"
            output_file = os.path.join(output_dir, output_filename)
            img.save(output_file)

            # Calculate compression efficiency
            compression_ratio = compressed_size / original_size
            compression_percentage = (1 - compression_ratio) * 100

            self.update_progress(100)
            self.status_label.config(text=f"File converted to image successfully: {output_file}\n"
                                          f"Original Size: {original_size} bytes\n"
                                          f"Compressed Size: {compressed_size} bytes\n"
                                          f"Compression Efficiency: {compression_percentage:.2f}%")
        except Exception as e:
            logging.error("Error in convert_file_to_image: %s", e)
            messagebox.showerror("Error", str(e))

    def convert_image_to_file(self):
        input_file = self.input_file_entry.get()
        output_dir = self.output_location_entry.get()
        if not input_file or not output_dir:
            messagebox.showerror("Error", "Please select an image and output location.")
            return

        try:
            self.update_progress(0)
            
            # Open the image
            img = Image.open(input_file)

            # Convert image to binary data
            binary_data = create_binary_from_image(img)

            self.update_progress(50)
            byte_data = int(binary_data, 2).to_bytes((len(binary_data) + 7) // 8, byteorder='big')

            # Decompress the data
            decompressed_data = decompress_data(byte_data)

            # Write the decompressed data to file
            base_filename = os.path.basename(input_file)
            output_filename = os.path.splitext(base_filename)[0] + ".output"
            output_file = os.path.join(output_dir, output_filename)
            with open(output_file, "wb") as f:
                f.write(decompressed_data)

            self.update_progress(100)
            self.status_label.config(text=f"Image converted to file successfully: {output_file}")
        except Exception as e:
            logging.error("Error in convert_image_to_file: %s", e)
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    root = tk.Tk()
    app = ByteMapApp(root)
    root.mainloop()
