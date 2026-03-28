import os
import re
import time
import threading
import subprocess

import numpy as np
import sounddevice as sd

from config import CURRENT_CONFIG, EL_CLIENT


class TTSEngine:
    """Manages the TTS queue and speaks text via ElevenLabs, Piper, or espeak."""

    def __init__(self, interrupted_event):
        self.interrupted = interrupted_event
        self._queue      = []
        self._lock       = threading.Lock()
        self._active     = threading.Event()   # set while a line is being spoken
        self._thinking   = threading.Event()   # set while thinking sounds loop
        self.current_audio_process = None
        self.current_volume        = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        threading.Thread(target=self._worker, daemon=True).start()

    # ── Queue API ─────────────────────────────────────────────────────────────

    def enqueue(self, text):
        with self._lock:
            self._queue.append(text)

    def clear_queue(self):
        with self._lock:
            self._queue.clear()

    def wait_for_completion(self):
        """Block until the queue is empty and nothing is playing."""
        while True:
            with self._lock:
                empty = not self._queue
            if empty and not self._active.is_set():
                break
            if self.interrupted.is_set():
                break
            time.sleep(0.1)

    def stop_current(self):
        self._thinking.clear()
        self.clear_queue()
        if self.current_audio_process:
            try:
                self.current_audio_process.terminate()
            except:
                pass

    # ── Thinking sounds ───────────────────────────────────────────────────────

    def start_thinking_sounds(self):
        self._thinking.set()
        threading.Thread(target=self._thinking_sound_loop, daemon=True).start()

    def stop_thinking_sounds(self):
        self._thinking.clear()

    def _thinking_sound_loop(self):
        time.sleep(2.0)
        phrases = ["Think, think, think...", "Hmm, let me think...", "Oh, just a moment..."]
        idx = 0
        while self._thinking.is_set():
            self.speak(phrases[idx % len(phrases)])
            idx += 1
            for _ in range(50):
                if not self._thinking.is_set():
                    return
                time.sleep(0.1)

    # ── Internal worker ───────────────────────────────────────────────────────

    def _worker(self):
        while True:
            text = None
            with self._lock:
                if self._queue:
                    text = self._queue.pop(0)
            if text:
                self._active.set()
                self.speak(text)
                self._active.clear()
            else:
                time.sleep(0.05)

    # ── Speaking ──────────────────────────────────────────────────────────────

    def speak(self, text):
        clean = re.sub(r"[^\w\s,.!?:-]", "", text)
        if not clean.strip():
            return

        use_piper = CURRENT_CONFIG.get("use_piper_tts", True)
        el_key = os.getenv("ELEVENLABS_API_KEY", CURRENT_CONFIG.get("elevenlabs_api_key", "")).strip()

        if el_key and not use_piper:
            self._speak_elevenlabs(clean)
        else:
            self._speak_piper(clean)

    def _speak_elevenlabs(self, clean):
        print(f"[ELEVENLABS] '{clean}'", flush=True)
        voice_id = CURRENT_CONFIG.get("elevenlabs_voice_id", "Rachel")
        try:
            audio_stream = EL_CLIENT.text_to_speech.stream(
                voice_id=voice_id,
                text=clean,
                model_id="eleven_turbo_v2_5",
                output_format="pcm_22050",
            )
            PCM_RATE = 22050
            with sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16",
                                    device=None, latency="low", blocksize=2048) as stream:
                for chunk in audio_stream:
                    if self.interrupted.is_set():
                        break
                    if chunk:
                        audio_chunk = np.frombuffer(chunk, dtype=np.int16)
                        self.current_volume = int(np.max(np.abs(audio_chunk))) if len(audio_chunk) else 0
                        stream.write(chunk)
        except Exception as e:
            print(f"[ELEVENLABS] Error: {e}")
        finally:
            self.current_volume = 0

    def _speak_piper(self, clean):
        print(f"[PIPER] '{clean}'", flush=True)
        piper_model = CURRENT_CONFIG.get("piper_model", "./piper/en_GB-semaine-medium.onnx")
        piper_bin   = "./piper/piper"

        if not os.path.exists(piper_bin) or not os.path.exists(piper_model):
            print("[PIPER] Not found, falling back to espeak", flush=True)
            self._speak_espeak(clean)
            return

        try:
            proc = subprocess.Popen(
                [piper_bin, "--model", piper_model, "--output_raw"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            )
            self.current_audio_process = proc
            raw_audio, _ = proc.communicate(input=clean.encode())
            if raw_audio and not self.interrupted.is_set():
                audio = np.frombuffer(raw_audio, dtype=np.int16)
                self.current_volume = int(np.max(np.abs(audio))) if len(audio) else 0
                sd.play(audio, samplerate=22050)
                sd.wait()
        except Exception as e:
            print(f"[PIPER] Error: {e}, falling back to espeak")
            self._speak_espeak(clean)
        finally:
            self.current_volume = 0
            self.current_audio_process = None

    def _speak_espeak(self, clean):
        print(f"[ESPEAK] '{clean}'", flush=True)
        try:
            proc = subprocess.Popen(
                ["espeak-ng", "-v", "en", "-s", "145", "-a", "180", clean],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            self.current_audio_process = proc
            proc.wait()
        except Exception as e:
            print(f"[ESPEAK] Error: {e}")
        finally:
            self.current_audio_process = None
