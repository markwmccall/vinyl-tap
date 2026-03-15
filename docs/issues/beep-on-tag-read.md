# Feature: Audible beep when a tag is read and queued to Sonos

## Summary

After a successful NFC tag scan queues an album/track/playlist to Sonos,
play a short audible beep so the user gets immediate physical confirmation
without looking at a screen.

The beep should fire **after** `play_album` / `play_playlist` returns
successfully in `core/nfc_service.py` (the current `log.info("Playing …")`
line is the right insertion point).

---

## Hardware constraint

The **Raspberry Pi Zero 2 W has no built-in analog audio jack** (unlike the
Pi 3B+/4). Any audio approach must either add hardware or re-use hardware
that is already present.

---

## Options

### Option A — USB audio dongle + `aplay` (WAV via subprocess)

**Hardware:** Any cheap USB audio adapter (~$5) plugged into the Pi Zero's
USB port (via micro-USB OTG adapter).

**How it works:**
- Generate a sine-wave WAV entirely in Python (`wave` + `struct` + `math` —
  zero new pip dependencies).
- Pipe it to `aplay -q -` via `subprocess.Popen` (non-blocking fire-and-forget).
- Gracefully no-ops if `aplay` is not found (dev/mock environments).

**Pros:**
- No new Python dependencies.
- Clean stereo audio quality.
- Easy to swap the beep for any WAV (e.g. a more musical chime).

**Cons:**
- Requires a USB OTG adapter + USB audio dongle.
- Occupies the Pi Zero's only USB port (unless using a hub).

**Rough implementation sketch:**

```python
# core/beep.py
import io, math, struct, subprocess, wave

_SAMPLE_RATE = 44100

def _generate_wav(frequency=880, duration_ms=150, volume=0.4):
    n = int(_SAMPLE_RATE * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(_SAMPLE_RATE)
        w.writeframes(b"".join(
            struct.pack("<h", int(volume * 32767 * math.sin(2 * math.pi * frequency * i / _SAMPLE_RATE)))
            for i in range(n)
        ))
    return buf.getvalue()

def beep(frequency=880, duration_ms=150, volume=0.4):
    try:
        p = subprocess.Popen(["aplay", "-q", "-"],
                             stdin=subprocess.PIPE,
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        p.stdin.write(_generate_wav(frequency, duration_ms, volume))
        p.stdin.close()
    except (FileNotFoundError, OSError):
        pass
```

---

### Option B — Passive buzzer on GPIO (PWM tone)

**Hardware:** One passive buzzer (~$1) wired between a free GPIO pin (e.g.
GPIO 23) and GND. The NFC HAT uses GPIO 4 (chip-select) and GPIO 20 (reset),
so GPIO 23 / GPIO 24 are available.

> **Passive buzzer** (not active): requires a PWM signal to produce a tone.
> Active buzzers produce a fixed frequency when powered and cannot be
> pitch-controlled.

**How it works:**
- Use `RPi.GPIO` (already available on Pi OS) or `gpiozero` to drive a PWM
  signal on the pin for ~150 ms, then stop.
- Run in a daemon thread or `threading.Timer` so it doesn't block the NFC loop.

**Pros:**
- No USB port consumed.
- Extremely cheap and reliable hardware.
- Works completely offline — no ALSA/audio subsystem needed.
- Tone frequency/duration tunable in code.

**Cons:**
- New dependency: `RPi.GPIO` or `gpiozero` (both are pre-installed on Pi OS,
  but need adding to `requirements.txt` for the venv).
- Requires a small hardware addition and two-wire soldering/breadboard.
- `RPi.GPIO` / `gpiozero` not available on dev machines → mock required for tests.

**Rough implementation sketch:**

```python
# core/beep.py
import threading

_BEEP_PIN = 23  # BCM GPIO 23 — change to match your wiring

def beep(frequency=880, duration_ms=150):
    def _play():
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(_BEEP_PIN, GPIO.OUT)
            pwm = GPIO.PWM(_BEEP_PIN, frequency)
            pwm.start(50)  # 50% duty cycle
            threading.Event().wait(duration_ms / 1000)
            pwm.stop()
            GPIO.cleanup(_BEEP_PIN)
        except (ImportError, RuntimeError):
            pass  # not on Pi hardware or RPi.GPIO unavailable
    threading.Thread(target=_play, daemon=True).start()
```

---

### Option C — PWM audio on GPIO 18 via ALSA (no extra hardware)

**Hardware:** None beyond the Pi itself. Requires a speaker or headphones
wired directly to GPIO 18 (and GPIO 19 for stereo) via a simple RC filter
and 3.5mm jack breakout.

**How it works:**
- Enable `dtoverlay=pwm-2chan` in `/boot/config.txt`.
- Configure an ALSA `snd-pwm` virtual device.
- Then `aplay` works exactly as in Option A.

**Pros:**
- No USB port consumed.
- No buzzer required — standard headphones work.

**Cons:**
- Significant setup work (kernel overlay, ALSA config).
- Audio quality is poor (PWM noise floor).
- Fragile: depends on Pi OS ALSA config surviving updates.
- The RC filter + wiring is fiddly.
- **Not recommended** unless there is already a speaker wired this way.

---

### Option D — I2S DAC HAT (e.g. HiFiBerry DAC Zero)

**Hardware:** A DAC HAT that sits on the GPIO header (e.g. HiFiBerry DAC
Zero, ~$25).

**Pros:**
- High-quality audio.
- `aplay` works as in Option A once the overlay is configured.

**Cons:**
- **Conflicts with the Waveshare PN532 NFC HAT** which already occupies the
  GPIO header.
- Expensive relative to the feature.
- **Not viable** without a GPIO expander or custom board.

---

## Recommended approach

**Option B (passive buzzer)** for the simplest, most reliable, always-on
feedback with minimal cost.

**Option A (USB audio dongle)** if higher-quality audio or future sound
effects (chimes, album art tones) are desirable — at the cost of the USB
port.

Options C and D are not recommended for this project.

---

## Integration point in code

```python
# core/nfc_service.py  — inside _nfc_loop, after successful playback:

            play_album(...)   # or play_playlist(...)
            log.info("Playing %s %s", tag["type"], tag["id"])
            beep()            # ← add here
```

The beep is intentionally **after** the Sonos call so it only fires on
success, not on provider/network errors.

---

## Testing strategy

- `core/beep.py` — unit tests mock `subprocess.Popen` (Option A) or
  `RPi.GPIO` / `gpiozero` (Option B); verify graceful no-op when unavailable.
- `nfc_service._nfc_loop` — existing test class gains one test:
  `test_beep_called_after_successful_play` patching `core.nfc_service.beep`.
