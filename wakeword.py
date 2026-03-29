import os
import sys
import select
import time
import wave
import tempfile

import numpy as np
import scipy.signal
import sounddevice as sd
from openwakeword.model import Model

from config import WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD, INPUT_DEVICE_NAME
from audio_processing import preprocess_chunk
from whisper_utils import WAKE_LISTEN_CHUNK, WAKE_MIN_PEAK, WAKE_PHRASES, transcribe_file, whisper_ready


class WakeWordDetector:
    def __init__(self):
        self.model = None
        self.mode = "ptt"
        print("[INIT] Loading Wake Word...", flush=True)

        if os.path.exists(WAKE_WORD_MODEL):
            try:
                self.model = Model(wakeword_model_paths=[WAKE_WORD_MODEL])
                self.mode = "openwakeword"
                print("[INIT] Wake Word Loaded.", flush=True)
                return
            except TypeError:
                try:
                    self.model = Model(wakeword_models=[WAKE_WORD_MODEL])
                    self.mode = "openwakeword"
                    print("[INIT] Wake Word Loaded (New API).", flush=True)
                    return
                except Exception as e:
                    print(f"[WARN] Failed to load ONNX wake model: {e}", flush=True)
            except Exception as e:
                print(f"[WARN] Failed to load ONNX wake model: {e}", flush=True)
        else:
            print(f"[WARN] Model not found: {WAKE_WORD_MODEL}", flush=True)

        if whisper_ready():
            self.mode = "whisper"
            print("[INIT] Using whisper.cpp fallback for 'Hey Pooh'.", flush=True)
        else:
            print("[WARN] No wake-word model available. Falling back to push-to-talk.", flush=True)

    def detect(self, ptt_event):
        """Block until a trigger. Returns 'WAKE', 'PTT', or 'CLI'."""
        if self.mode == "openwakeword" and self.model:
            self.model.reset()

        if self.mode == "openwakeword":
            return self._detect_openwakeword(ptt_event)

        if self.mode == "whisper":
            return self._detect_whisper(ptt_event)

        if self.model is None:
            ptt_event.wait()
            ptt_event.clear()
            return "PTT"

    def _check_external_triggers(self, ptt_event):
        if ptt_event.is_set():
            ptt_event.clear()
            return "PTT"

        try:
            rlist, _, _ = select.select([sys.stdin], [], [], 0.001)
            if rlist:
                sys.stdin.readline()
                return "CLI"
        except Exception:
            pass

        return None

    def _detect_openwakeword(self, ptt_event):
        CHUNK_SIZE      = 1280
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
                    external_trigger = self._check_external_triggers(ptt_event)
                    if external_trigger:
                        return external_trigger

                    data, _ = stream.read(input_chunk_size)
                    audio_data = np.frombuffer(data, dtype=np.int16)

                    if use_resampling:
                        audio_data = scipy.signal.resample(audio_data, CHUNK_SIZE).astype(np.int16)

                    # Preprocess for better wake word detection
                    float_audio = audio_data.astype(np.float32) / 32767.0
                    float_audio = preprocess_chunk(float_audio, OWW_SAMPLE_RATE)
                    audio_data = (float_audio * 32767).astype(np.int16)

                    self.model.predict(audio_data)
                    for mdl in self.model.prediction_buffer:
                        if list(self.model.prediction_buffer[mdl])[-1] > WAKE_WORD_THRESHOLD:
                            self.model.reset()
                            return "WAKE"
        except Exception as e:
            print(f"Wake Word Stream Error: {e}")
            ptt_event.wait()
            return "PTT"

    def _detect_whisper(self, ptt_event):
        try:
            samplerate = int(sd.query_devices(kind="input")["default_samplerate"])
        except:
            samplerate = 44100

        while True:
            external_trigger = self._check_external_triggers(ptt_event)
            if external_trigger:
                return external_trigger

            try:
                audio = sd.rec(int(samplerate * WAKE_LISTEN_CHUNK), samplerate=samplerate,
                               channels=1, dtype="float32", device=INPUT_DEVICE_NAME)
                sd.wait()
            except Exception as e:
                print(f"Whisper Wake Stream Error: {e}", flush=True)
                time.sleep(0.3)
                continue

            audio = preprocess_chunk(audio.flatten(), samplerate).reshape(-1, 1).astype(np.float32)
            peak = float(np.max(np.abs(audio))) if audio.size else 0.0
            if peak < WAKE_MIN_PEAK:
                continue

            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                    temp_path = temp_file.name

                pcm_audio = np.nan_to_num(audio.flatten(), nan=0.0, posinf=0.0, neginf=0.0)
                pcm_audio = (pcm_audio * 32767).astype(np.int16)

                with wave.open(temp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(samplerate)
                    wf.writeframes(pcm_audio.tobytes())

                heard_text = transcribe_file(temp_path, timeout=max(15, int(WAKE_LISTEN_CHUNK * 6))).lower()
                if heard_text:
                    print(f"[WAKE HEARD] '{heard_text}'", flush=True)

                if any(phrase in heard_text for phrase in WAKE_PHRASES):
                    print("[WAKE] Hey Pooh detected via whisper.cpp", flush=True)
                    return "WAKE"
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
