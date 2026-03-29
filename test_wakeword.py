"""Wake word test — listens for "hey pooh" and cycles through face animations."""

import os
import time
import wave
import threading
import subprocess
import tkinter as tk

import numpy as np
import sounddevice as sd
from PIL import Image, ImageTk


# ── Settings ────────────────────────────────────────────────────────────────
WAKE_PHRASES = ["hey pooh", "hey poo", "hey puh", "a]pooh", "hey po", "hey boo", "hey poooh"]
BG_WIDTH, BG_HEIGHT = 800, 480
WHISPER_CLI = "./whisper.cpp/build/bin/whisper-cli"
WHISPER_MODEL = "./whisper.cpp/models/ggml-base.en.bin"
LISTEN_CHUNK = 3  # seconds per chunk to check for wake word
SILENCE_THRESHOLD = 0.003
RECORD_SILENCE_SECS = 1.5
RECORD_MAX_SECS = 15


# ── Face loader ─────────────────────────────────────────────────────────────
def load_faces():
    faces = {}
    for state in ["idle", "listening", "thinking", "speaking", "warmup", "error"]:
        folder = os.path.join("faces", state)
        faces[state] = []
        if os.path.exists(folder):
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
            for f in files:
                img = Image.open(os.path.join(folder, f)).resize((BG_WIDTH, BG_HEIGHT))
                faces[state].append(ImageTk.PhotoImage(img))
        if not faces[state]:
            blank = Image.new("RGB", (BG_WIDTH, BG_HEIGHT), "#0000FF")
            faces[state].append(ImageTk.PhotoImage(blank))
    return faces


# ── Whisper transcription ───────────────────────────────────────────────────
def transcribe(filename):
    if not os.path.exists(WHISPER_CLI):
        print(f"[ERROR] whisper-cli not found at {WHISPER_CLI}")
        return ""
    try:
        result = subprocess.run(
            [WHISPER_CLI, "-m", WHISPER_MODEL, "-l", "en", "-t", "4",
             "--no-prints", "-f", filename],
            capture_output=True, text=True, timeout=10,
        )
        text = result.stdout.strip()
        # Get last line, strip timestamp if present
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if lines:
            last = lines[-1]
            return last.split("]")[1].strip() if "]" in last else last
        return ""
    except Exception as e:
        print(f"[TRANSCRIBE ERROR] {e}")
        return ""


# ── Audio helpers ───────────────────────────────────────────────────────────
def get_samplerate():
    try:
        return int(sd.query_devices(kind="input")["default_samplerate"])
    except:
        return 44100


def save_wav(buffer, filename, samplerate):
    if not buffer:
        return None
    audio = np.concatenate(buffer, axis=0).flatten()
    audio = np.nan_to_num(audio, nan=0.0)
    audio = (audio * 32767).astype(np.int16)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(audio.tobytes())
    return filename


def record_chunk(duration, samplerate):
    """Record a short chunk and return as numpy array."""
    audio = sd.rec(int(samplerate * duration), samplerate=samplerate,
                   channels=1, dtype="float32")
    sd.wait()
    # Boost mic gain 3x for better sensitivity
    audio = audio * 3.0
    audio = np.clip(audio, -1.0, 1.0)
    return audio


def record_until_silence(samplerate):
    """Record until silence detected, return saved filename."""
    print("[RECORDING] Speak now...", flush=True)
    chunk_dur = 0.05
    chunk_size = int(samplerate * chunk_dur)
    num_silent = int(RECORD_SILENCE_SECS / chunk_dur)
    max_chunks = int(RECORD_MAX_SECS / chunk_dur)

    buffer = []
    silent_count = 0
    total = 0
    done = False

    def callback(indata, frames, time_info, status):
        nonlocal silent_count, total, done
        buffer.append(indata.copy())
        total += 1
        if total < 5:
            return
        vol = np.linalg.norm(indata) / np.sqrt(len(indata))
        if vol < SILENCE_THRESHOLD:
            silent_count += 1
            if silent_count >= num_silent:
                done = True
        else:
            silent_count = 0

    try:
        with sd.InputStream(samplerate=samplerate, channels=1, callback=callback,
                            blocksize=chunk_size):
            while not done and total < max_chunks:
                sd.sleep(int(chunk_dur * 1000))
    except Exception as e:
        print(f"[RECORD ERROR] {e}")
        return None

    return save_wav(buffer, "input.wav", samplerate)


# ── Main app ────────────────────────────────────────────────────────────────
class WakeWordTestApp:
    def __init__(self, master):
        self.master = master
        self.state = "idle"
        self.frame_idx = 0

        master.title("Hey Pooh - Wake Word Test")
        master.attributes("-fullscreen", True)
        master.bind("<Escape>", lambda e: self.shutdown())

        self.label = tk.Label(master, bg="black")
        self.label.place(x=0, y=0, width=BG_WIDTH, height=BG_HEIGHT)

        # Volume bar
        self.vol_canvas = tk.Canvas(master, height=20, bg="#111111", highlightthickness=0)
        self.vol_canvas.place(relx=0.05, rely=0.88, relwidth=0.9, anchor=tk.W)
        self.vol_bar = self.vol_canvas.create_rectangle(0, 0, 0, 20, fill="#00ff00")
        self.vol_label = tk.Label(master, text="VOL: 0.0000", font=("Arial", 10),
                                  fg="#aaaaaa", bg="black")
        self.vol_label.place(relx=0.5, rely=0.85, anchor=tk.S)

        self.info = tk.Label(master, text="", font=("Arial", 20), fg="white", bg="black")
        self.info.place(relx=0.5, rely=0.95, anchor=tk.S)

        self.faces = load_faces()
        self.samplerate = get_samplerate()

        # Check whisper
        if not os.path.exists(WHISPER_CLI):
            self.set_info("ERROR: whisper-cli not found! Build whisper.cpp first.")
            self.set_state("error")
            return

        self.animate()
        threading.Thread(target=self.listen_loop, daemon=True).start()

    def set_state(self, state):
        self.state = state
        self.frame_idx = 0

    def set_info(self, text):
        self.master.after(0, lambda: self.info.config(text=text))

    def update_volume(self, peak):
        def _update():
            bar_width = int(min(peak * 500, 1.0) * self.vol_canvas.winfo_width())
            # Color: green → yellow → red
            if peak < 0.05:
                color = "#00ff00"
            elif peak < 0.2:
                color = "#ffff00"
            else:
                color = "#ff0000"
            self.vol_canvas.coords(self.vol_bar, 0, 0, bar_width, 20)
            self.vol_canvas.itemconfig(self.vol_bar, fill=color)
            self.vol_label.config(text=f"VOL: {peak:.4f}")
        self.master.after(0, _update)

    def animate(self):
        import random
        frames = self.faces.get(self.state, self.faces["idle"])
        if frames:
            if self.state == "speaking" and len(frames) > 1:
                self.frame_idx = random.randint(0, len(frames) - 1)
            else:
                self.frame_idx = (self.frame_idx + 1) % len(frames)
            self.master.after(0, lambda: self.label.config(image=frames[self.frame_idx]))

        speed = 80 if self.state == "speaking" else 500
        self.master.after(speed, self.animate)

    def listen_loop(self):
        """Continuously listen for 'hey pooh' using whisper."""
        print("=== Listening for 'Hey Pooh' ===", flush=True)
        self.set_state("idle")
        self.set_info("Say 'Hey Pooh' to wake me up!")

        while True:
            # Record a short chunk
            audio = record_chunk(LISTEN_CHUNK, self.samplerate)
            peak = np.max(np.abs(audio))

            # Update volume bar
            self.update_volume(peak)
            print(f"[VOL] peak={peak:.4f}", flush=True)

            # Skip if too quiet (no one talking)
            if peak < 0.001:
                continue

            # Save and transcribe the chunk
            save_wav([audio], "wake_check.wav", self.samplerate)
            text = transcribe("wake_check.wav")
            text_lower = text.lower().strip()
            print(f"[HEARD] '{text_lower}'", flush=True)

            # Check for wake phrase
            if any(phrase in text_lower for phrase in WAKE_PHRASES):
                print("[WAKE] Hey Pooh detected!", flush=True)
                self.handle_conversation()

    def handle_conversation(self):
        """Full flow: listening → thinking → speaking → idle."""
        # LISTENING
        self.set_state("listening")
        self.set_info("I'm listening!")
        audio_file = record_until_silence(self.samplerate)

        if not audio_file:
            self.set_info("Didn't hear anything...")
            self.set_state("idle")
            self.set_info("Say 'Hey Pooh' to wake me up!")
            return

        # THINKING
        self.set_state("thinking")
        self.set_info("Think, think, think...")
        text = transcribe(audio_file)
        print(f"[YOU SAID] '{text}'", flush=True)

        if not text.strip():
            self.set_state("idle")
            self.set_info("Say 'Hey Pooh' to wake me up!")
            return

        # SPEAKING (simulate response for now)
        self.set_state("speaking")
        self.set_info(f"You said: {text[:50]}")
        time.sleep(3)

        # Back to IDLE
        self.set_state("idle")
        self.set_info("Say 'Hey Pooh' to wake me up!")

    def shutdown(self):
        # Clean up temp files
        for f in ["wake_check.wav"]:
            if os.path.exists(f):
                os.remove(f)
        self.master.destroy()


if __name__ == "__main__":
    print("=== Hey Pooh - Wake Word Test ===")
    print("Press Escape to exit\n")
    root = tk.Tk()
    app = WakeWordTestApp(root)
    root.mainloop()
