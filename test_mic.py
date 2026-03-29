"""Quick mic test — checks if the Pi can hear you."""

import sounddevice as sd
import numpy as np
import subprocess

print("=== Microphone Test ===\n")

# Try to set USB mic capture to max via amixer (safe, silently skipped if unavailable)
try:
    subprocess.run(["amixer", "sset", "Capture", "100%"], capture_output=True)
    subprocess.run(["amixer", "sset", "Mic", "100%"], capture_output=True)
    subprocess.run(["amixer", "sset", "Mic Capture Volume", "100%"], capture_output=True)
except Exception:
    pass

# List all audio devices
print("Audio devices:")
print(sd.query_devices())
print()

# Check default input
try:
    dev = sd.query_devices(kind="input")
    print(f"Default input: {dev['name']}")
    print(f"Sample rate: {int(dev['default_samplerate'])}")
except Exception as e:
    print(f"ERROR: No input device found: {e}")
    exit(1)

# Record 3 seconds
print("\nRecording 3 seconds... speak now!")
samplerate = int(dev["default_samplerate"])
duration = 3
audio = sd.rec(int(samplerate * duration), samplerate=samplerate, channels=1, dtype="float32")
sd.wait()

raw = audio.flatten()

# Raw stats
peak_raw = float(np.max(np.abs(raw)))
rms_raw  = float(np.sqrt(np.mean(raw ** 2)))

# AGC-boosted stats (what Whisper/wake detector actually receives)
try:
    from audio_processing import preprocess_chunk
    boosted = preprocess_chunk(raw, samplerate)
    peak_boosted = float(np.max(np.abs(boosted)))
    rms_boosted  = float(np.sqrt(np.mean(boosted ** 2)))
    show_boosted = True
except Exception:
    show_boosted = False

print(f"\n--- Raw (hardware level) ---")
print(f"  Peak: {peak_raw:.4f}")
print(f"  RMS:  {rms_raw:.6f}")

if show_boosted:
    print(f"\n--- After AGC (what Whisper hears) ---")
    print(f"  Peak: {peak_boosted:.4f}")
    print(f"  RMS:  {rms_boosted:.6f}")

print()
if peak_raw > 0.01:
    print("  Mic is WORKING — audio detected.")
    if show_boosted and peak_boosted > 0.05:
        print("  AGC level is GOOD — Whisper should detect speech fine.")
    elif show_boosted:
        print("  WARNING: AGC level still low. Mic may be too quiet for reliable wake detection.")
else:
    print("  WARNING: Very low raw audio. Check mic connection or try a different USB port.")

print("\nDone!")
