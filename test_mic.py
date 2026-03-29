"""Quick mic test — checks if the Pi can hear you."""

import sounddevice as sd
import numpy as np
import time

print("=== Microphone Test ===\n")

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

# Check volume
peak = np.max(np.abs(audio))
rms = np.sqrt(np.mean(audio**2))
print(f"\nResults:")
print(f"  Peak volume: {peak:.4f}")
print(f"  RMS volume:  {rms:.6f}")

if peak > 0.01:
    print("\n  Mic is WORKING! Audio detected.")
else:
    print("\n  WARNING: Very low audio. Check mic connection.")

print("\nDone!")
