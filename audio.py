import wave
import time

import numpy as np
import sounddevice as sd

from config import INPUT_DEVICE_NAME


# ── Recording ─────────────────────────────────────────────────────────────────

def save_audio_buffer(buffer, filename, samplerate=16000):
    """Flatten and write a buffer list to a WAV file. Returns filename or None."""
    if not buffer:
        return None
    audio_data = np.concatenate(buffer, axis=0).flatten()
    audio_data = np.nan_to_num(audio_data, nan=0.0, posinf=0.0, neginf=0.0)
    audio_data = (audio_data * 32767).astype(np.int16)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio_data.tobytes())
    return filename


def record_voice_adaptive(filename="input.wav"):
    """Record until silence is detected or max time is reached."""
    print("Recording (Adaptive)...", flush=True)
    time.sleep(0.5)

    try:
        samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
    except:
        samplerate = 44100

    silence_threshold = 0.006
    silence_duration  = 1.5
    max_record_time   = 30.0
    chunk_duration    = 0.05

    chunk_size        = int(samplerate * chunk_duration)
    num_silent_chunks = int(silence_duration / chunk_duration)
    max_chunks        = int(max_record_time / chunk_duration)

    buffer          = []
    silent_chunks   = 0
    recorded_chunks = 0
    silence_started = False

    def callback(indata, frames, time_info, status):
        nonlocal silent_chunks, recorded_chunks, silence_started
        buffer.append(indata.copy())
        recorded_chunks += 1
        if recorded_chunks < 5:
            return
        volume_norm = np.linalg.norm(indata) / np.sqrt(len(indata))
        if volume_norm < silence_threshold:
            silent_chunks += 1
            if silent_chunks >= num_silent_chunks:
                silence_started = True
        else:
            silent_chunks = 0

    try:
        with sd.InputStream(samplerate=samplerate, channels=1, callback=callback,
                            device=INPUT_DEVICE_NAME, blocksize=chunk_size):
            while not silence_started and recorded_chunks < max_chunks:
                sd.sleep(int(chunk_duration * 1000))
    except:
        return None

    return save_audio_buffer(buffer, filename, samplerate)


def record_voice_ptt(recording_active_event, filename="input.wav"):
    """Record while recording_active_event is set (push-to-talk)."""
    print("Recording (PTT)...", flush=True)
    time.sleep(0.5)

    try:
        samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
    except:
        samplerate = 44100

    buffer = []

    def callback(indata, frames, time_info, status):
        buffer.append(indata.copy())

    try:
        with sd.InputStream(samplerate=samplerate, channels=1, callback=callback,
                            device=INPUT_DEVICE_NAME):
            while recording_active_event.is_set():
                sd.sleep(50)
    except:
        return None

    return save_audio_buffer(buffer, filename, samplerate)
