"""
Gesture Handler - processes IMU events and triggers audio, display and LED actions.

- 1 tap   -> play/pause
- 2 taps  -> volume up
- 3 taps  -> volume down
- Rotate cube CW/CCW (about Z axis) -> next/previous song
- Shake          -> power on/off
"""
import time, threading, logging
log = logging.getLogger("gesture")

DEBOUNCE  = 0.4
LOOP_RATE = 0.05

VOLUME_DISPLAY_TIME = 1.5  # seconds to show volume before reverting to song

class GestureHandler:
    def __init__(self, imu, audio, display, leds):
        self.imu     = imu
        self.audio   = audio
        self.display = display
        self.leds    = leds
        self._running      = False
        self._powered_on   = True
        self._last_gesture = 0.0

    def start_loop(self):
        self._running = True
        log.info("Gesture loop started")
        while self._running:
            if not self._powered_on:
                if self.imu.event_shake:
                    self._power_on()
                    self.imu.event_shake = False
                time.sleep(LOOP_RATE)
                continue
            self._process_events()
            time.sleep(LOOP_RATE)

    def stop(self):
        self._running = False

    def _process_events(self):
        imu, now = self.imu, time.time()
        debounce_ok = (now - self._last_gesture) > DEBOUNCE

        if imu.event_shake:
            imu.event_shake = False
            self._power_off()
            return

        if not debounce_ok:
            return

        if imu.event_play_pause:
            imu.event_play_pause = False
            self._last_gesture   = now
            self._play_pause()

        if imu.event_volume_up:
            imu.event_volume_up = False
            self._last_gesture  = now
            self._volume_up()

        if imu.event_volume_down:
            imu.event_volume_down = False
            self._last_gesture    = now
            self._volume_down()

        if imu.event_next_song:
            imu.event_next_song = False
            self._last_gesture   = now
            self._next_song()

        if imu.event_prev_song:
            imu.event_prev_song = False
            self._last_gesture   = now
            self._prev_song()

    def _play_pause(self):
        self.audio.play_pause()
        playing = self.audio.is_playing()
        log.info(f"Play/pause -> {'playing' if playing else 'paused'}")
        self.leds.flash(0, 1, 0) if playing else self.leds.flash(1, 0.5, 0)
        self.display.show_song(self.audio.current_song())

    def _next_song(self):
        self.audio.next_song()
        log.info(f"Next song: {self.audio.current_song()}")
        self.display.show_song(self.audio.current_song())
        self.leds.flash(0, 0, 1)

    def _prev_song(self):
        self.audio.prev_song()
        log.info(f"Prev song: {self.audio.current_song()}")
        self.display.show_song(self.audio.current_song())
        self.leds.flash(1, 0, 1)

    def _volume_up(self):
        vol = self.audio.volume_up()
        log.info(f"Volume up: {vol}%")
        self.display.show_volume(vol)
        self.leds.flash(1, 1, 0)
        self._schedule_revert_to_song()

    def _volume_down(self):
        vol = self.audio.volume_down()
        log.info(f"Volume down: {vol}%")
        self.display.show_volume(vol)
        self.leds.flash(1, 1, 0)
        self._schedule_revert_to_song()

    def _schedule_revert_to_song(self):
        """After showing volume briefly, go back to the song screen."""
        def revert():
            self.display.show_song(self.audio.current_song())
        threading.Timer(VOLUME_DISPLAY_TIME, revert).start()

    def _power_off(self):
        log.info("Powering off")
        self._powered_on = False
        self.audio.pause()
        self.display.clear_all()
        self.leds.set_color(0, 0, 0)

    def _power_on(self):
        log.info("Powering on")
        self._powered_on = True
        self.display.show_song(self.audio.current_song())
        self.leds.flash(0, 1, 0)
