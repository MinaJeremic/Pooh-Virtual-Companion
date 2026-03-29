"""Audio preprocessing pipeline for improving mic quality on Raspberry Pi."""

import numpy as np
from scipy.signal import butter, sosfilt


def highpass_filter(audio, samplerate, cutoff=80, order=4):
    """Remove low-frequency rumble below cutoff Hz."""
    if len(audio) < order * 3:
        return audio
    sos = butter(order, cutoff, btype='high', fs=samplerate, output='sos')
    return sosfilt(sos, audio).astype(audio.dtype)


def apply_agc(audio, target_rms=0.1, max_gain=10.0):
    """Automatic gain control — normalize volume to a consistent level."""
    rms = np.sqrt(np.mean(audio ** 2))
    if rms < 1e-6:
        return audio
    gain = min(target_rms / rms, max_gain)
    return np.clip(audio * gain, -1.0, 1.0)


def noise_gate(audio, threshold=0.01):
    """Suppress audio below threshold to kill ambient hiss."""
    mask = np.abs(audio) > threshold
    return audio * mask


def preprocess_chunk(audio, samplerate):
    """Quick preprocessing for real-time chunks (wake word, silence detection)."""
    audio = highpass_filter(audio, samplerate)
    audio = apply_agc(audio)
    return audio


def preprocess_buffer(audio, samplerate):
    """Full preprocessing for recorded audio before saving to WAV."""
    audio = highpass_filter(audio, samplerate)
    audio = noise_gate(audio)
    audio = apply_agc(audio)
    try:
        import noisereduce as nr
        audio = nr.reduce_noise(y=audio, sr=samplerate, prop_decrease=0.8)
    except ImportError:
        pass
    return audio
