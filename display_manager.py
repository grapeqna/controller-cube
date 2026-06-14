"""
Display Manager
Controls all 5 SSD1306 OLED screens via TCA9548A.
- Channel 0: current song (top face)
- Channels 1-4: static image / decorative
"""

import time
import threading
import logging
import board
import busio
import adafruit_tca9548a
from adafruit_ssd1306 import SSD1306_I2C
from PIL import Image, ImageDraw, ImageFont
from i2c_lock import i2c_lock

log = logging.getLogger("display")

SCREEN_CHANNELS = [0, 1, 2, 3, 4]
SONG_CHANNEL    = 0
WIDTH  = 128
HEIGHT = 64


class DisplayManager:
    def __init__(self):
        i2c = busio.I2C(board.SCL, board.SDA)
        tca = adafruit_tca9548a.TCA9548A(i2c)

        self.screens = {}
        for ch in SCREEN_CHANNELS:
            try:
                self.screens[ch] = SSD1306_I2C(WIDTH, HEIGHT, tca[ch])
                log.info(f"Display on channel {ch} ready")
            except Exception as e:
                log.warning(f"Display channel {ch} failed: {e}")

        self._lock = threading.Lock()
        self._show_decorative_screens()

    # ── Public API ────────────────────────────────────────────────

    def show_song(self, song: dict):
        """Show current song title and artist on the song screen."""
        title  = song.get("title",  "Unknown")
        artist = song.get("artist", "Unknown")
        self._draw_song(title, artist)

    def show_volume(self, level: int):
        """Briefly show volume level on the song screen."""
        self._draw_text_screen(SONG_CHANNEL, f"Volume", f"{level}%")

    def show_reorient_countdown(self, seconds: float):
        """Show a countdown on the song screen during reorient window."""
        def countdown():
            start = time.time()
            while True:
                remaining = seconds - (time.time() - start)
                if remaining <= 0:
                    break
                self._draw_text_screen(SONG_CHANNEL, "Reorienting...", f"{remaining:.1f}s")
                time.sleep(0.1)
        threading.Thread(target=countdown, daemon=True).start()

    def show_all(self, message: str):
        """Show the same message on all screens."""
        for ch in self.screens:
            self._draw_text_screen(ch, message, "")

    def clear_all(self):
        """Turn off all screens."""
        with self._lock, i2c_lock:
            for oled in self.screens.values():
                try:
                    oled.fill(0)
                    oled.show()
                except Exception:
                    pass

    # ── Drawing ───────────────────────────────────────────────────

    def _draw_song(self, title: str, artist: str):
        if SONG_CHANNEL not in self.screens:
            return
        with self._lock, i2c_lock:
            try:
                oled  = self.screens[SONG_CHANNEL]
                image = Image.new("1", (WIDTH, HEIGHT))
                draw  = ImageDraw.Draw(image)

                # Title (truncate if too long)
                if len(title) > 16:
                    title = title[:15] + "…"
                if len(artist) > 16:
                    artist = artist[:15] + "…"

                draw.text((2, 4),  title,  font=None, fill=255)
                draw.text((2, 22), artist, font=None, fill=255)

                # Simple divider line
                draw.line([(0, 18), (WIDTH, 18)], fill=255, width=1)

                oled.image(image)
                oled.show()
            except Exception as e:
                log.warning(f"Draw song failed: {e}")

    def _draw_text_screen(self, channel: int, line1: str, line2: str):
        if channel not in self.screens:
            return
        with self._lock, i2c_lock:
            try:
                oled  = self.screens[channel]
                image = Image.new("1", (WIDTH, HEIGHT))
                draw  = ImageDraw.Draw(image)
                draw.text((2, 20), line1, font=None, fill=255)
                draw.text((2, 36), line2, font=None, fill=255)
                oled.image(image)
                oled.show()
            except Exception as e:
                log.warning(f"Draw text failed on channel {channel}: {e}")

    def _show_decorative_screens(self):
        """Show a simple pattern on the non-song screens."""
        for ch in self.screens:
            if ch == SONG_CHANNEL:
                continue
            try:
                oled  = self.screens[ch]
                image = Image.new("1", (WIDTH, HEIGHT))
                draw  = ImageDraw.Draw(image)
                # Simple border decoration
                draw.rectangle([(0, 0), (WIDTH-1, HEIGHT-1)], outline=255)
                draw.rectangle([(3, 3), (WIDTH-4, HEIGHT-4)], outline=255)
                draw.text((30, 26), "MUSIC CUBE", font=None, fill=255)
                oled.image(image)
                oled.show()
            except Exception as e:
                log.warning(f"Decorative screen {ch} failed: {e}")
