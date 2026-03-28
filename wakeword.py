import os
import sys
import select

import numpy as np
import scipy.signal
import sounddevice as sd
from openwakeword.model import Model

from config import WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD, INPUT_DEVICE_NAME


class WakeWordDetector:
    def __init__(self):
        self.model = None
        print("[INIT] Loading Wake Word...", flush=True)

        if not os.path.exists(WAKE_WORD_MODEL):
            print(f"[CRITICAL] Model not found: {WAKE_WORD_MODEL}")
            return

        try:
            self.model = Model(wakeword_model_paths=[WAKE_WORD_MODEL])
            print("[INIT] Wake Word Loaded.", flush=True)
        except TypeError:
            try:
                self.model = Model(wakeword_models=[WAKE_WORD_MODEL])
                print("[INIT] Wake Word Loaded (New API).", flush=True)
            except Exception as e:
                print(f"[CRITICAL] Failed to load model: {e}")
        except Exception as e:
            print(f"[CRITICAL] Failed to load model: {e}")

    def detect(self, ptt_event):
        """Block until a trigger. Returns 'WAKE', 'PTT', or 'CLI'."""
        if self.model:
            self.model.reset()

        if self.model is None:
            ptt_event.wait()
            ptt_event.clear()
            return "PTT"

        CHUNK_SIZE     = 1280
        OWW_SAMPLE_RATE = 16000

        try:
            native_rate = int(sd.query_devices(kind="input")["default_samplerate"])
        except:
            native_rate = 48000

        use_resampling   = (native_rate != OWW_SAMPLE_RATE)
        input_rate       = native_rate if use_resampling else OWW_SAMPLE_RATE
        input_chunk_size = int(CHUNK_SIZE * (input_rate / OWW_SAMPLE_RATE)) if use_resampling else CHUNK_SIZE

        try:
            with sd.InputStream(samplerate=input_rate, channels=1, dtype="int16",
                                blocksize=input_chunk_size, device=INPUT_DEVICE_NAME) as stream:
                while True:
                    if ptt_event.is_set():
                        ptt_event.clear()
                        return "PTT"

                    rlist, _, _ = select.select([sys.stdin], [], [], 0.001)
                    if rlist:
                        sys.stdin.readline()
                        return "CLI"

                    data, _ = stream.read(input_chunk_size)
                    audio_data = np.frombuffer(data, dtype=np.int16)

                    if use_resampling:
                        audio_data = scipy.signal.resample(audio_data, CHUNK_SIZE).astype(np.int16)

                    self.model.predict(audio_data)
                    for mdl in self.model.prediction_buffer:
                        if list(self.model.prediction_buffer[mdl])[-1] > WAKE_WORD_THRESHOLD:
                            self.model.reset()
                            return "WAKE"
        except Exception as e:
            print(f"Wake Word Stream Error: {e}")
            ptt_event.wait()
            return "PTT"
