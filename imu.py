import time, math, threading, logging
import board, busio, adafruit_tca9548a
from i2c_lock import i2c_lock

log = logging.getLogger("imu")

MPU_CHANNEL     = 5
G               = 9.8
SAMPLE_RATE     = 0.05

TAP_X_THRESHOLD = 1.0
TAP_WINDOW      = 1.2
SHAKE_THRESHOLD = 22.0
SHAKE_DURATION  = 0.6

# Multi-tap (side) settings for volume control
SIDE_TAP_DEBOUNCE = 0.35  # min seconds between counted taps
MULTI_TAP_EVAL    = 1   # seconds of silence after the last tap before evaluating the group
BASELINE_ALPHA    = 0.05  # how fast the resting baseline adapts (lower = slower)

# Gyro-based rotation suppression: while the cube is physically rotating,
# accelerometer spikes are from the rotation itself, not taps.
ROTATION_GYRO_THRESHOLD = 1.0   # rad/s - above this counts as "rotating"
ROTATION_COOLDOWN       = 0.4   # seconds after rotation stops before taps resume

# Orientation (face) detection
FACE_THRESHOLD  = 6.0   # ax or ay must exceed this to count as "dominant"
FACE_STABLE     = 0.5   # new orientation must hold steady this long before locking in

# Clockwise order of orientations, based on the calibration described above
ORIENTATION_CYCLE = ["negY_up", "posX_up", "posY_up", "negX_up"]


class IMUController:
    def __init__(self):
        self._running  = False
        self._lock     = threading.Lock()
        self.available = False

        self.accel = (0.0, 0.0, G)
        self.gyro  = (0.0, 0.0, 0.0)

        self.event_play_pause  = False   # fires on a 1-tap group
        self.event_volume_up   = False   # fires on a 2-tap group
        self.event_volume_down = False   # fires on a 3-tap group
        self.event_shake       = False
        self.event_next_song   = False
        self.event_prev_song   = False

        self._tap_x_history     = []
        self._shake_start       = None
        self._last_tap_time     = 0

        # Side-tap counting for multi-tap volume control
        self._side_tap_count    = 0
        self._last_side_tap_time = 0

        # Rotation tracking (from gyro) - used to suppress tap detection
        self._last_rotation_time = 0

        # Orientation tracking - None means "not yet determined", will be
        # set from the first confident reading instead of assumed
        self._current_orientation = None
        self._pending_orientation = None
        self._pending_since        = None

        # Rolling baseline for tap detection (so taps are detected as
        # deviation from "resting", regardless of which axis gravity
        # currently sits on)
        self._ax_baseline = None
        self._ay_baseline = None
        self._az_baseline = None

        try:
            import adafruit_mpu6050
            i2c = busio.I2C(board.SCL, board.SDA)
            tca = adafruit_tca9548a.TCA9548A(i2c)
            self.mpu = adafruit_mpu6050.MPU6050(tca[MPU_CHANNEL])
            self.available = True
            log.info("MPU6050 ready on channel 5")
        except Exception as e:
            self.mpu = None
            log.warning(f"MPU6050 not available: {e}")

    def start_loop(self):
        self._running = True
        if not self.available:
            log.warning("IMU loop skipped, no sensor found")
            return

        log.info("IMU loop started")
        while self._running:
            try:
                with i2c_lock:
                    ax, ay, az = self.mpu.acceleration
                    gx, gy, gz = self.mpu.gyro
                with self._lock:
                    self.accel = (ax, ay, az)
                    self.gyro  = (gx, gy, gz)

                self._update_baseline(ax, ay, az)
                self._detect_rotation(gx, gy, gz)
                self._detect_side_tap(ax, ay, az)
                self._evaluate_side_tap_group()
                self._detect_shake(ax, ay, az)
                self._detect_orientation(ax, ay)
            except Exception as e:
                log.warning(f"IMU read error: {e}")
                time.sleep(1.0)
            time.sleep(SAMPLE_RATE)

    def stop(self):
        self._running = False

    # ── Resting baseline (for orientation-independent tap detection) ──

    def _detect_rotation(self, gx, gy, gz):
        """Track whether the cube is currently being physically rotated,
        using the gyroscope. While rotating (and briefly after), tap
        detection is suppressed since accelerometer spikes during a
        roll aren't intentional taps."""
        magnitude = math.sqrt(gx**2 + gy**2 + gz**2)
        if magnitude > ROTATION_GYRO_THRESHOLD:
            self._last_rotation_time = time.time()

    def _is_rotating(self):
        return (time.time() - self._last_rotation_time) < ROTATION_COOLDOWN


    def _update_baseline(self, ax, ay, az):
        """Slowly track the 'resting' acceleration on each axis.
        Whichever axis currently has gravity on it will settle near
        +-G, the others near 0. A real tap is a brief deviation
        away from this baseline, regardless of orientation."""
        if self._ax_baseline is None:
            # first reading - initialize directly, no smoothing
            self._ax_baseline = ax
            self._ay_baseline = ay
            self._az_baseline = az
            return

        self._ax_baseline += BASELINE_ALPHA * (ax - self._ax_baseline)
        self._ay_baseline += BASELINE_ALPHA * (ay - self._ay_baseline)
        self._az_baseline += BASELINE_ALPHA * (az - self._az_baseline)

    # ── Orientation / song change ────────────────────────────────

    def _current_orientation_from(self, ax, ay):
        """Return which axis is currently pointing 'up' based on ax/ay only."""
        if abs(ax) < FACE_THRESHOLD and abs(ay) < FACE_THRESHOLD:
            return None  # not confident enough, cube might be moving

        if abs(ay) >= abs(ax):
            return "negY_up" if ay < 0 else "posY_up"
        else:
            return "posX_up" if ax > 0 else "negX_up"

    def _detect_orientation(self, ax, ay):
        now = time.time()
        detected = self._current_orientation_from(ax, ay)

        if detected is None:
            self._pending_orientation = None
            self._pending_since = None
            return

        if self._current_orientation is None:
            # first confident reading, just set it, don't treat as a rotation
            self._current_orientation = detected
            log.info(f"Initial orientation detected: {detected}")
            return

        if detected == self._current_orientation:
            self._pending_orientation = None
            self._pending_since = None
            return

        if detected != self._pending_orientation:
            self._pending_orientation = detected
            self._pending_since = now
            return

        if now - self._pending_since >= FACE_STABLE:
            self._lock_in_orientation(detected)
            self._pending_orientation = None
            self._pending_since = None

    def _lock_in_orientation(self, new_orientation):
        old_idx = ORIENTATION_CYCLE.index(self._current_orientation)
        new_idx = ORIENTATION_CYCLE.index(new_orientation)

        diff = (new_idx - old_idx) % 4

        with self._lock:
            if diff == 1:
                self.event_next_song = True
                log.info(f"Orientation {self._current_orientation} -> {new_orientation}: NEXT song")
            elif diff == 3:
                self.event_prev_song = True
                log.info(f"Orientation {self._current_orientation} -> {new_orientation}: PREV song")
            else:
                log.info(f"Orientation jumped {self._current_orientation} -> {new_orientation} (diff={diff}), ignoring")

        self._current_orientation = new_orientation

    # ── Taps / shake ──────────────────────────────────────────────

    def _detect_side_tap(self, ax, ay, az):
        """Detect any sharp tap on the X axis (either side) and add it
        to a running count. Detection is based on deviation from the
        slow-moving resting baseline, so it works regardless of which
        axis gravity currently sits on. The actual volume/play action
        is decided later by _evaluate_side_tap_group() once taps stop
        coming in."""
        if self._ax_baseline is None:
            return  # baseline not established yet

        now = time.time()
        if now - self._last_tap_time < SIDE_TAP_DEBOUNCE:
            return  # debounce a single physical tap

        deviation = ax - self._ax_baseline
        self._tap_x_history.append((now, deviation))
        self._tap_x_history = [(t, v) for t, v in self._tap_x_history if now - t < TAP_WINDOW]
        values = [v for _, v in self._tap_x_history]
        if not values:
            return

        if max(values) > TAP_X_THRESHOLD or min(values) < -TAP_X_THRESHOLD:
            self._tap_x_history.clear()
            self._last_tap_time = now
            self._side_tap_count += 1
            self._last_side_tap_time = now
            log.info(f"Side tap detected ({self._side_tap_count} so far)")

            if self._side_tap_count >= 3:
                if self._is_rotating():
                    log.info("Rotation detected after 3 taps, discarding (likely noise from spin)")
                else:
                    log.info("Too many taps in a row, resetting")
                self._side_tap_count = 0

    def _evaluate_side_tap_group(self):
        """After a short pause with no new taps, decide what the
        accumulated tap count means:
          2 taps -> volume up
          3 taps -> volume down
          anything else -> ignored
        """
        if self._side_tap_count == 0:
            return

        now = time.time()
        if now - self._last_side_tap_time < MULTI_TAP_EVAL:
            return  # still waiting to see if another tap comes in

        count = self._side_tap_count
        self._side_tap_count = 0

        if count == 1:
            with self._lock:
                self.event_play_pause = True
            log.info("Single tap -> play/pause")
        elif count == 2:
            with self._lock:
                self.event_volume_up = True
            log.info("Double tap -> volume up")
        elif count == 3:
            with self._lock:
                self.event_volume_down = True
            log.info("Triple tap -> volume down")
        else:
            log.info(f"{count} tap(s) detected, no action assigned")

    def _detect_shake(self, ax, ay, az):
        magnitude = math.sqrt(ax**2 + ay**2 + az**2)
        now = time.time()
        if magnitude > SHAKE_THRESHOLD:
            if self._shake_start is None:
                self._shake_start = now
            elif now - self._shake_start >= SHAKE_DURATION:
                with self._lock:
                    self.event_shake = True
                self._shake_start = None
                log.info("Shake detected")
        else:
            self._shake_start = None
