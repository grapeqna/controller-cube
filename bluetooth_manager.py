import time, subprocess, logging
log = logging.getLogger("bluetooth")

class BluetoothManager:
    def __init__(self):
        self._connected = False
        self._setup_bluetooth()

    def _setup_bluetooth(self):
        for cmd in [
            ["bluetoothctl", "power", "on"],
            ["bluetoothctl", "discoverable", "on"],
            ["bluetoothctl", "pairable", "on"],
            ["bluetoothctl", "agent", "NoInputNoOutput"],
            ["bluetoothctl", "default-agent"],
        ]:
            try:
                subprocess.run(cmd, capture_output=True, timeout=5)
            except Exception as e:
                log.warning(f"BT setup command failed: {e}")
        log.info("Bluetooth ready, waiting for connection...")

    def is_connected(self):
        try:
            result = subprocess.run(["bluetoothctl", "info"], capture_output=True, text=True, timeout=5)
            return "Connected: yes" in result.stdout
        except Exception:
            return False

    def wait_for_connection(self, poll_interval=2.0):
        while not self.is_connected():
            log.info("No Bluetooth device connected yet, retrying...")
            time.sleep(poll_interval)
        self._connected = True
        log.info("Bluetooth device connected!")
