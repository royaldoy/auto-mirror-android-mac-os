import rumps
import subprocess
import json
import time
import threading
import os
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
ICON_PATH = os.path.join(BASE_DIR, "icon.png")
ADB_PATH = os.path.join(BASE_DIR, "adb")
SCRCPY_PATH = os.path.join(BASE_DIR, "scrcpy")

class AutoScrcpyApp(rumps.App):
    def __init__(self):
        print("[INFO] Initializing app...")
        super().__init__("", icon=ICON_PATH, menu=[])
        self.config = self.load_config()
        self.running = False
        self.connected = False
        self.worker = None
        self.scrcpy_proc = None
        self.prompt_pending = False  # Untuk trigger alert di main thread

        self.status_item = rumps.MenuItem("⏸️ Paused")
        self.toggle_item = rumps.MenuItem("Turn On", callback=self.toggle_monitoring)
        self.quit_item = rumps.MenuItem("Quit", callback=rumps.quit_application)
        self.menu = [self.status_item, self.toggle_item, None, self.quit_item]

        self.alert_timer = rumps.Timer(self.prompt_user_to_mirror, 1)
        self.alert_timer.start()

        print("[INFO] Menu initialized.")

    def load_config(self):
        with open(CONFIG_PATH) as f:
            config = json.load(f)
            print("[INFO] Loaded config:", config)
            return config

    def set_status(self, text):
        self.status_item.title = text
        print(f"[STATUS] {text}")

    def update_toggle_label(self):
        self.toggle_item.title = "Turn On" if not self.running else "Turn Off"

    def ping_device(self, ip):
        try:
            print(f"[PING] Trying to connect to {ip} via ADB...")
            result = subprocess.run([ADB_PATH, "connect", ip], capture_output=True, text=True)
            print(f"[ADB] {result.stdout.strip()}")
            return "connected" in result.stdout.lower() or "already connected" in result.stdout.lower()
        except Exception as e:
            print(f"[ERROR] ADB connect failed: {e}")
            return False

    def connect_and_scrcpy(self):
        try:
            ip = self.config["device_ip"]
            bitrate = self.config.get("video_bitrate", "8M")
            max_size = str(self.config["max_size"])

            print(f"[ACTION] Connecting to ADB at {ip}...")
            subprocess.run([ADB_PATH, "connect", ip], capture_output=True)

            print(f"[ACTION] Launching scrcpy for {ip}...")
            self.scrcpy_proc = subprocess.Popen([
                SCRCPY_PATH,
                "--video-bit-rate", bitrate,
                "--max-size", max_size,
                "-s", ip
            ])
        except Exception as e:
            print(f"[ERROR] Failed to launch scrcpy: {e}")

    def background_check(self):
        while self.running:
            ip = self.config["device_ip"]
            if not self.connected and self.ping_device(ip):
                self.connected = True
                self.set_status("📱 Connected")
                print(f"[INFO] Device {ip} detected.")
                self.prompt_pending = True  # Trigger alert

            elif not self.ping_device(ip):
                if self.connected:
                    print(f"[INFO] Device {ip} disconnected.")
                self.connected = False
                self.set_status("🔍 Scanning...")

            time.sleep(self.config["check_interval"])

    def prompt_user_to_mirror(self, _):
        if self.prompt_pending:
            self.prompt_pending = False
            response = rumps.alert(
                "Perangkat terdeteksi",
                "Apakah ingin mirror dengan device ini?",
                ok="Ya", cancel="Tidak"
            )
            if response == 1:
                print("[INFO] User confirmed to start mirroring.")
                self.connect_and_scrcpy()
            else:
                print("[INFO] User cancelled mirroring.")

    def toggle_monitoring(self, _):
        self.running = not self.running
        self.update_toggle_label()
        if self.running:
            print("[START] Monitoring started.")
            self.set_status("🔍 Scanning...")
            self.worker = threading.Thread(target=self.background_check, daemon=True)
            self.worker.start()
        else:
            print("[STOP] Monitoring stopped.")
            self.set_status("⏸️ Paused")
            self.connected = False
            if self.scrcpy_proc and self.scrcpy_proc.poll() is None:
                print("[ACTION] Terminating scrcpy process...")
                self.scrcpy_proc.terminate()
                self.scrcpy_proc.wait()
                self.scrcpy_proc = None

if __name__ == "__main__":
    try:
        print("[INIT] AutoScrcpy launched.")
        app = AutoScrcpyApp()
        app.run()
    except Exception as e:
        print("[FATAL ERROR]", e)
        traceback.print_exc()
