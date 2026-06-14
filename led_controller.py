"""
GPIO 17 (R), 27 (G), 22 (B).
"""

import time
import threading
import logging
import RPi.GPIO as GPIO

log = logging.getLogger("leds")

PIN_R = 17
PIN_G = 27
PIN_B = 22


class LEDController:
    def __init__(self):
        GPIO.setmode(GPIO.BCM)
        GPIO.setup([PIN_R, PIN_G, PIN_B], GPIO.OUT)
        # Common anode: HIGH = off, LOW = on
        GPIO.output([PIN_R, PIN_G, PIN_B], GPIO.HIGH)
        self._lock   = threading.Lock()
        self._thread = None

    def set_color(self, r, g, b):
        self._cancel_animation()
        with self._lock:
            self._write(r, g, b)

    def flash(self, r, g, b, times=2, duration=0.1):
        self._cancel_animation()
        def _flash():
            for _ in range(times):
                with self._lock:
                    self._write(r, g, b)
                time.sleep(duration)
                with self._lock:
                    self._write(0, 0, 0)
                time.sleep(duration)
        self._thread = threading.Thread(target=_flash, daemon=True)
        self._thread.start()

    def pulse(self, r, g, b):
        self._cancel_animation()
        self._stop_pulse = False
        def _pulse():
            while not self._stop_pulse:
                with self._lock:
                    self._write(r, g, b)
                time.sleep(0.6)
                with self._lock:
                    self._write(0, 0, 0)
                time.sleep(0.4)
        self._thread = threading.Thread(target=_pulse, daemon=True)
        self._thread.start()

    def _write(self, r, g, b):
        # Common anode: invert logic
        GPIO.output(PIN_R, GPIO.LOW  if r else GPIO.HIGH)
        GPIO.output(PIN_G, GPIO.LOW  if g else GPIO.HIGH)
        GPIO.output(PIN_B, GPIO.LOW  if b else GPIO.HIGH)

    def _cancel_animation(self):
        self._stop_pulse = True
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def cleanup(self):
        self._cancel_animation()
        GPIO.output([PIN_R, PIN_G, PIN_B], GPIO.HIGH)
        GPIO.cleanup()
