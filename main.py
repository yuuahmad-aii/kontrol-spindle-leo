import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import struct

class ManualModbusController:
    """
    Kelas untuk mengelola komunikasi Modbus RTU secara manual dengan spindle.
    Menggunakan pyserial untuk komunikasi dan membuat frame Modbus sendiri.
    """
    def __init__(self, port=None, baudrate=38400, bytesize=8, parity='E', stopbits=1, slave_id=1):
        self.ser = None
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.slave_id = slave_id
        self.is_connected = False

    def connect(self):
        """Mencoba untuk membuat koneksi serial."""
        if self.ser and self.ser.is_open:
            self.disconnect()

        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=1
            )
            if self.ser.is_open:
                self.is_connected = True
                return True
            else:
                self.is_connected = False
                return False
        except serial.SerialException as e:
            self.is_connected = False
            print(f"Error connecting to serial port: {e}")
            return False

    def disconnect(self):
        """Menutup koneksi serial."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.is_connected = False
            return True
        return False

    @staticmethod
    def calculate_crc(data: bytes) -> bytes:
        """Menghitung checksum CRC-16 untuk data Modbus."""
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if (crc & 1) != 0:
                    crc >>= 1
                    crc ^= 0xA001
                else:
                    crc >>= 1
        # Mengembalikan CRC sebagai 2 byte (low byte, high byte)
        return struct.pack('<H', crc)

    def _send_modbus_rtu_frame(self, function_code, register_address, value):
        """
        Membuat dan mengirim frame Modbus RTU lengkap (Fungsi 0x06: Write Single Register).
        """
        if not self.is_connected:
            return False, "Tidak terhubung ke port serial."

        try:
            # 1. Bentuk PDU (Protocol Data Unit) tanpa Slave ID dan CRC
            # [Function Code (1 byte)] + [Register Address (2 bytes)] + [Value (2 bytes)]
            pdu = struct.pack('>BHH', function_code, register_address, value)

            # 2. Tambahkan Slave ID untuk membuat data yang akan di-CRC
            data_for_crc = struct.pack('B', self.slave_id) + pdu

            # 3. Hitung CRC
            crc = self.calculate_crc(data_for_crc)

            # 4. Gabungkan semua menjadi frame RTU lengkap
            rtu_frame = data_for_crc + crc

            # 5. Kirim frame melalui serial
            self.ser.flushInput()
            self.ser.flushOutput()
            self.ser.write(rtu_frame)

            # 6. (Opsional tapi direkomendasikan) Baca respons untuk konfirmasi
            # Untuk fungsi 06, respons yang berhasil adalah gema (echo) dari permintaan
            response = self.ser.read(len(rtu_frame))
            if response == rtu_frame:
                return True, "Perintah berhasil dikirim dan dikonfirmasi."
            elif len(response) > 0:
                return False, f"Respons tidak valid diterima: {response.hex()}"
            else:
                return False, "Tidak ada respons dari perangkat (timeout)."

        except serial.SerialException as e:
            return False, f"Serial Error: {e}"
        except Exception as e:
            return False, f"Error saat mengirim perintah: {e}"

    def start_cw(self):
        """Mengirim perintah untuk memutar spindle searah jarum jam (CW)."""
        # Register: 0x6000, Nilai: 1
        return self._send_modbus_rtu_frame(0x06, 0x6000, 1)

    def start_ccw(self):
        """Mengirim perintah untuk memutar spindle berlawanan arah jarum jam (CCW)."""
        # Register: 0x6000, Nilai: 2
        return self._send_modbus_rtu_frame(0x06, 0x6000, 2)

    def stop_spindle(self):
        """Mengirim perintah untuk menghentikan spindle (mengatur frekuensi ke 0)."""
        # Register: 0x5000, Nilai: 0
        return self._send_modbus_rtu_frame(0x06, 0x5000, 0)

    def set_frequency(self, frequency_value):
        """Mengirim perintah untuk mengatur frekuensi spindle."""
        if not isinstance(frequency_value, int) or frequency_value < 0:
            return False, "Nilai frekuensi harus bilangan bulat positif."
        # Register: 0x5000, Nilai: frequency_value
        return self._send_modbus_rtu_frame(0x06, 0x5000, frequency_value)


class SpindleGUI:
    """
    Kelas untuk membuat antarmuka pengguna grafis (GUI) untuk mengontrol spindle.
    """
    def __init__(self, master):
        self.master = master
        master.title("Kontrol Spindle Modbus (Manual)")
        master.geometry("400x500") # Menyesuaikan tinggi jendela untuk field baru
        master.resizable(False, False)

        self.controller = ManualModbusController()
        self.create_widgets()
        self.update_port_list()

    def create_widgets(self):
        """Membuat dan menata widget GUI."""
        # Frame Koneksi
        connection_frame = ttk.LabelFrame(self.master, text="Pengaturan Koneksi Modbus")
        connection_frame.pack(padx=10, pady=10, fill="x")

        ttk.Label(connection_frame, text="Port Serial:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.port_combobox = ttk.Combobox(connection_frame, width=20, state="readonly")
        self.port_combobox.grid(row=0, column=1, padx=5, pady=2, sticky="ew")
        self.port_combobox.bind("<<ComboboxSelected>>", self.on_port_selected)

        ttk.Label(connection_frame, text="Baud Rate:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.baudrate_entry = ttk.Entry(connection_frame, width=20)
        self.baudrate_entry.insert(0, "38400")
        self.baudrate_entry.grid(row=1, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(connection_frame, text="Slave ID:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.slave_id_entry = ttk.Entry(connection_frame, width=20)
        self.slave_id_entry.insert(0, "1")
        self.slave_id_entry.grid(row=2, column=1, padx=5, pady=2, sticky="ew")

        # --- WIDGET BARU UNTUK PARITY DAN STOP BITS ---
        ttk.Label(connection_frame, text="Parity:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
        self.parity_combobox = ttk.Combobox(connection_frame, width=20, values=['Even', 'Odd', 'None', 'Mark', 'Space'], state="readonly")
        self.parity_combobox.set('Even')
        self.parity_combobox.grid(row=3, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(connection_frame, text="Stop Bits:").grid(row=4, column=0, padx=5, pady=2, sticky="w")
        self.stopbits_combobox = ttk.Combobox(connection_frame, width=20, values=[1, 1.5, 2], state="readonly")
        self.stopbits_combobox.set(1)
        self.stopbits_combobox.grid(row=4, column=1, padx=5, pady=2, sticky="ew")
        # --- AKHIR WIDGET BARU ---

        self.connect_button = ttk.Button(connection_frame, text="Hubungkan", command=self.connect_modbus)
        self.connect_button.grid(row=6, column=0, columnspan=1, padx=5, pady=10, sticky="ew")
        self.disconnect_button = ttk.Button(connection_frame, text="Putuskan", command=self.disconnect_modbus, state=tk.DISABLED)
        self.disconnect_button.grid(row=6, column=1, columnspan=1, padx=5, pady=10, sticky="ew")

        # Frame Kontrol Spindle
        control_frame = ttk.LabelFrame(self.master, text="Kontrol Spindle")
        control_frame.pack(padx=10, pady=10, fill="x")

        self.cw_button = ttk.Button(control_frame, text="CW (Searah Jarum Jam)", command=self.on_cw_click, state=tk.DISABLED)
        self.cw_button.grid(row=0, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        self.ccw_button = ttk.Button(control_frame, text="CCW (Berlawanan Jarum Jam)", command=self.on_ccw_click, state=tk.DISABLED)
        self.ccw_button.grid(row=1, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        ttk.Label(control_frame, text="Frekuensi (Hz):").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.frequency_entry = ttk.Entry(control_frame, width=15)
        self.frequency_entry.insert(0, "0")
        self.frequency_entry.grid(row=2, column=1, padx=5, pady=2, sticky="ew")

        self.set_frequency_button = ttk.Button(control_frame, text="Atur Frekuensi", command=self.on_set_frequency_click, state=tk.DISABLED)
        self.set_frequency_button.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        self.stop_button = ttk.Button(control_frame, text="Hentikan Spindle", command=self.on_stop_click, state=tk.DISABLED)
        self.stop_button.grid(row=4, column=0, columnspan=2, padx=5, pady=5, sticky="ew")

        # Status Bar
        self.status_label = ttk.Label(self.master, text="Status: Tidak terhubung", relief=tk.SUNKEN, anchor="w")
        self.status_label.pack(side=tk.BOTTOM, fill="x")

    def update_port_list(self):
        """Memperbarui daftar port serial yang tersedia."""
        ports = serial.tools.list_ports.comports()
        self.available_ports = [port.device for port in ports]
        self.port_combobox['values'] = self.available_ports
        if self.available_ports:
            self.port_combobox.set(self.available_ports[0])
            self.controller.port = self.available_ports[0]
        else:
            self.port_combobox.set("Tidak ada port")
            self.controller.port = None

    def on_port_selected(self, event):
        """Menangani pemilihan port dari combobox."""
        selected_port = self.port_combobox.get()
        self.controller.port = selected_port
        self.update_status(f"Port dipilih: {selected_port}", "blue")

    def connect_modbus(self):
        """Menangani tombol 'Hubungkan'."""
        port = self.port_combobox.get()
        baudrate_str = self.baudrate_entry.get()
        slave_id_str = self.slave_id_entry.get()
        
        # --- MEMBACA NILAI DARI WIDGET BARU ---
        parity_str = self.parity_combobox.get()
        stopbits_str = self.stopbits_combobox.get()
        
        parity_map = {'None': 'N', 'Even': 'E', 'Odd': 'O', 'Mark': 'M', 'Space': 'S'}

        if not port or port == "Tidak ada port":
            messagebox.showerror("Error Koneksi", "Pilih port serial yang valid.")
            return

        try:
            baudrate = int(baudrate_str)
            slave_id = int(slave_id_str)
            stopbits = float(stopbits_str)
        except ValueError:
            messagebox.showerror("Error Input", "Baud Rate, Slave ID, dan Stop Bits harus berupa angka yang valid.")
            return

        if parity_str not in parity_map:
            messagebox.showerror("Error Input", "Nilai Parity tidak valid.")
            return
        
        parity = parity_map[parity_str]

        if stopbits not in [1, 1.5, 2]:
             messagebox.showerror("Error Input", "Nilai Stop Bits tidak valid.")
             return

        # --- MEMPERBARUI PENGATURAN CONTROLLER ---
        self.controller.port = port
        self.controller.baudrate = baudrate
        self.controller.parity = parity
        self.controller.stopbits = stopbits
        self.controller.slave_id = slave_id

        self.update_status("Mencoba menghubungkan...", "orange")
        threading.Thread(target=self._connect_modbus_thread, daemon=True).start()

    def _connect_modbus_thread(self):
        """Fungsi koneksi yang berjalan di thread terpisah."""
        if self.controller.connect():
            status_msg = f"Terhubung ke {self.controller.port} @ {self.controller.baudrate}, {self.controller.parity}, {self.controller.stopbits}"
            self.update_status(status_msg, "green")
            self.set_connection_widgets_state(tk.DISABLED)
            self.set_control_state(tk.NORMAL)
        else:
            self.update_status("Gagal terhubung. Periksa pengaturan atau koneksi.", "red")
            self.set_connection_widgets_state(tk.NORMAL)
            self.set_control_state(tk.DISABLED)

    def disconnect_modbus(self):
        """Menangani tombol 'Putuskan'."""
        self.update_status("Memutuskan koneksi...", "orange")
        if self.controller.disconnect():
            self.update_status("Koneksi terputus.", "red")
            self.set_connection_widgets_state(tk.NORMAL)
            self.set_control_state(tk.DISABLED)
        else:
            self.update_status("Tidak ada koneksi aktif untuk diputuskan.", "red")

    def on_cw_click(self):
        """Menangani tombol 'CW'."""
        self.update_status("Mengirim perintah CW...", "blue")
        success, message = self.controller.start_cw()
        self.update_status(f"CW: {message}", "green" if success else "red")

    def on_ccw_click(self):
        """Menangani tombol 'CCW'."""
        self.update_status("Mengirim perintah CCW...", "blue")
        success, message = self.controller.start_ccw()
        self.update_status(f"CCW: {message}", "green" if success else "red")

    def on_set_frequency_click(self):
        """Menangani tombol 'Atur Frekuensi'."""
        freq_str = self.frequency_entry.get()
        try:
            frequency = int(freq_str)
            if frequency < 0:
                raise ValueError("Frekuensi tidak boleh negatif.")
            self.update_status(f"Mengirim frekuensi: {frequency}...", "blue")
            success, message = self.controller.set_frequency(frequency)
            self.update_status(f"Set Frekuensi: {message}", "green" if success else "red")
        except ValueError:
            messagebox.showerror("Error Input", "Frekuensi harus berupa bilangan bulat positif.")
            self.update_status("Input frekuensi tidak valid.", "red")

    def on_stop_click(self):
        """Menangani tombol 'Hentikan Spindle'."""
        self.update_status("Mengirim perintah Hentikan Spindle (Frekuensi 0)...", "blue")
        success, message = self.controller.stop_spindle()
        self.update_status(f"Hentikan Spindle: {message}", "green" if success else "red")
        self.frequency_entry.delete(0, tk.END)
        self.frequency_entry.insert(0, "0")

    def set_control_state(self, state):
        """Mengatur status (aktif/nonaktif) tombol kontrol spindle."""
        self.cw_button.config(state=state)
        self.ccw_button.config(state=state)
        self.set_frequency_button.config(state=state)
        self.stop_button.config(state=state)
        self.frequency_entry.config(state='normal' if state == tk.NORMAL else 'disabled')


    def set_connection_widgets_state(self, state):
        """Mengatur status widget koneksi."""
        # 'readonly' untuk combobox agar tetap bisa dilihat tapi tidak bisa diubah
        widget_state = 'readonly' if state == tk.DISABLED else 'normal'
        entry_state = 'disabled' if state == tk.DISABLED else 'normal'

        self.port_combobox.config(state=widget_state)
        self.baudrate_entry.config(state=entry_state)
        self.slave_id_entry.config(state=entry_state)
        self.parity_combobox.config(state=widget_state)
        self.stopbits_combobox.config(state=widget_state)
        
        self.connect_button.config(state=state)
        self.disconnect_button.config(state=tk.NORMAL if state == tk.DISABLED else tk.DISABLED)

    def update_status(self, message, color="black"):
        """Memperbarui label status di GUI secara thread-safe."""
        def _update():
            self.status_label.config(text=f"Status: {message}", foreground=color)
        # Menjadwalkan pembaruan di main thread tkinter
        self.master.after(0, _update)

def main():
    root = tk.Tk()
    app = SpindleGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
