import time, threading, logging
from bluetooth_manager import BluetoothManager
from imu import IMUController
from display_manager import DisplayManager
from led_controller import LEDController
from audio_controller import AudioController
from gesture_handler import GestureHandler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("main")

def main():
    log.info("Music Cube starting up...")
    bt      = BluetoothManager()
    audio   = AudioController()
    display = DisplayManager()
    leds    = LEDController()
    imu     = IMUController()

    display.show_all("Waiting for BT...")
    leds.set_color(0, 0, 1)

    log.info("Waiting for Bluetooth connection...")
    bt.wait_for_connection()
    log.info("Bluetooth connected!")

    leds.set_color(0, 1, 0)
    time.sleep(0.5)
    leds.set_color(0, 0, 0)

    gesture = GestureHandler(imu, audio, display, leds)

    imu_thread     = threading.Thread(target=imu.start_loop, daemon=True)
    gesture_thread = threading.Thread(target=gesture.start_loop, daemon=True)
    imu_thread.start()
    gesture_thread.start()

    log.info("Music Cube ready.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down...")
        imu.stop()
        gesture.stop()
        display.clear_all()
        leds.set_color(0, 0, 0)

if __name__ == "__main__":
    main()
