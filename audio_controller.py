"""
Audio Controller - controls Bluetooth playback via playerctl and volume via softvol.
"""
import subprocess, logging
log = logging.getLogger("audio")
VOLUME_STEP = 5
VOLUME_MIN  = 0
VOLUME_MAX  = 100
ALSA_CARD   = "hw:3,0"   # HifiBerry DAC (PCM5102A)

class AudioController:
    def __init__(self):
        self._volume  = 50
        self._playing = False
        self._song    = "Unknown"
        self._artist  = "Unknown"
        self._set_volume(self._volume)

    def play_pause(self):
        self._run(["playerctl", "play-pause"])
        self._playing = not self._playing

    def pause(self):
        self._run(["playerctl", "pause"])
        self._playing = False

    def next_song(self):
        self._run(["playerctl", "next"])
        self._refresh_metadata()

    def prev_song(self):
        self._run(["playerctl", "previous"])
        self._refresh_metadata()

    def is_playing(self):
        try:
            result = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=3)
            self._playing = result.stdout.strip() == "Playing"
        except Exception:
            pass
        return self._playing

    def current_song(self):
        self._refresh_metadata()
        return {"title": self._song, "artist": self._artist}

    def _refresh_metadata(self):
        try:
            self._song   = subprocess.run(["playerctl", "metadata", "title"],  capture_output=True, text=True, timeout=3).stdout.strip() or "Unknown"
            self._artist = subprocess.run(["playerctl", "metadata", "artist"], capture_output=True, text=True, timeout=3).stdout.strip() or "Unknown"
        except Exception as e:
            log.warning(f"Metadata fetch failed: {e}")

    def volume_up(self):
        self._volume = min(VOLUME_MAX, self._volume + VOLUME_STEP)
        self._set_volume(self._volume)
        return self._volume

    def volume_down(self):
        self._volume = max(VOLUME_MIN, self._volume - VOLUME_STEP)
        self._set_volume(self._volume)
        return self._volume

    def _set_volume(self, level):
        try:
            # PCM5102A has no hardware volume control, use softvol via amixer on card 3
            subprocess.run(
                ["amixer", "-c", "3", "set", "PCM", f"{level}%"],
                capture_output=True, timeout=3
            )
        except Exception as e:
            log.warning(f"Volume set failed: {e}")

    def _run(self, cmd):
        try:
            subprocess.run(cmd, capture_output=True, timeout=5)
        except Exception as e:
            log.warning(f"Command {cmd} failed: {e}")
