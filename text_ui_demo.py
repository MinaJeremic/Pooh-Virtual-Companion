import io
import os
import queue
import random
import select
import sys
import textwrap
import threading
import time
import tkinter as tk
import webbrowser

from PIL import Image, ImageTk

from config import AI_CLIENT, AI_MODEL, SYSTEM_PROMPT

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def ask_ai(messages, user_text):
    msgs = messages + [{"role": "user", "content": user_text}]
    response = AI_CLIENT.chat.completions.create(
        model=AI_MODEL,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
        max_tokens=300,
    )
    text = (response.choices[0].message.content or "").strip()
    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": text})
    return text


def speak_elevenlabs(text):
    """
    Speak text via ElevenLabs TTS in a fire-and-forget background thread.
    Silently skips if no API key is configured or TTS deps missing.
    """
    def _run():
        try:
            from config import EL_CLIENT, CURRENT_CONFIG
            import sounddevice as sd
            import numpy as np
            import platform
            import shutil
            import subprocess
            import tempfile

                        def _play_in_browser_popup(audio_bytes):
                                # Optional mode: opens/refreshes a local browser tab with autoplay audio.
                                base = os.path.join(tempfile.gettempdir(), "pooh_audio_popup")
                                os.makedirs(base, exist_ok=True)
                                mp3_path = os.path.join(base, "latest.mp3")
                                html_path = os.path.join(base, "player.html")
                                with open(mp3_path, "wb") as f:
                                        f.write(audio_bytes)

                                html = """<!doctype html>
<html><head><meta charset='utf-8'><title>Pooh Audio</title></head>
<body style='font-family:Arial;background:#111;color:#fff;padding:20px'>
    <h3>Pooh Audio Output</h3>
    <p>If autoplay is blocked, press play once.</p>
    <audio id='a' controls autoplay style='width:100%'></audio>
    <script>
        const a = document.getElementById('a');
        a.src = 'latest.mp3?t=' + Date.now();
        a.play().catch(()=>{});
        setInterval(() => {
            const next = 'latest.mp3?t=' + Date.now();
            if (!a.paused && !a.ended) return;
            a.src = next;
            a.play().catch(()=>{});
        }, 1000);
    </script>
</body></html>"""
                                with open(html_path, "w", encoding="utf-8") as f:
                                        f.write(html)
                                webbrowser.open_new_tab("file://" + html_path)

            def _play_mp3_external(audio_bytes):
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(audio_bytes)
                    tmp = f.name
                try:
                    if platform.system() == "Darwin" and shutil.which("afplay"):
                        subprocess.run(["afplay", tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return
                    for player_cmd in (["mpg123", "-q"], ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet"], ["mpv", "--really-quiet"]):
                        if shutil.which(player_cmd[0]):
                            subprocess.run(player_cmd + [tmp], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            return
                    print("[TTS] No audio player found (need afplay/mpg123/ffplay/mpv).", flush=True)
                finally:
                    try:
                        os.unlink(tmp)
                    except Exception:
                        pass

            voice_id = CURRENT_CONFIG.get("elevenlabs_voice_id", "Rachel")
            audio_gen = EL_CLIENT.generate(
                text=text,
                voice=voice_id,
                model="eleven_monolingual_v1",
            )
            audio_bytes = b"".join(audio_gen)

            if os.getenv("AUDIO_POPUP", "0") == "1":
                _play_in_browser_popup(audio_bytes)
                return

            try:
                from pydub import AudioSegment
                seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
                samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
                samples /= float(1 << (8 * seg.sample_width - 1))
                if seg.channels == 2:
                    samples = samples.reshape(-1, 2)
                sd.play(samples, samplerate=seg.frame_rate)
                sd.wait()
            except Exception:
                _play_mp3_external(audio_bytes)
        except Exception as e:
            print(f"[TTS] {e}", flush=True)

    threading.Thread(target=_run, daemon=True).start()


def _paginate(text, chars_per_line=52, max_lines=3):
    """
    Split text into screen-sized pages (2D game dialogue style).
    Each page fits comfortably in the caption bar.
    """
    lines = textwrap.wrap(text, width=chars_per_line)
    pages = []
    for i in range(0, len(lines), max_lines):
        pages.append("\n".join(lines[i : i + max_lines]))
    return pages if pages else [text]


def run_terminal_only_demo():
    """Fallback when no display is available (SSH without DISPLAY)."""
    messages = []
    print("--- TERMINAL-ONLY POOH DEMO (no display found) ---", flush=True)
    print("Type and press Enter. Ctrl+C or 'quit' to exit.\n", flush=True)

    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye for now!", flush=True)
            return

        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            print("Bye for now!", flush=True)
            return

        print("[FACE -> LISTENING]", flush=True)
        time.sleep(0.3)
        print("[FACE -> THINKING]", flush=True)

        try:
            answer = ask_ai(messages, user_text)
        except Exception as e:
            print(f"[ERROR] {e}", flush=True)
            continue

        print("[FACE -> SPEAKING]", flush=True)
        print("\n[Pooh] ", end="", flush=True)
        for ch in answer:
            print(ch, end="", flush=True)
            time.sleep(0.018)
        print("\n", flush=True)
        print("[FACE -> IDLE]", flush=True)


# ─────────────────────────────────────────────
# GUI class
# ─────────────────────────────────────────────

class TextFaceDemo:
    BG_WIDTH, BG_HEIGHT = 800, 480
    SESSION_TIMEOUT_SECONDS = 5 * 60
    BLINK_INTERVAL_SECONDS = 45.0
    BLINK_DURATION_SECONDS = 0.22

    # Face animation speeds (ms per frame)
    SPEED_SPEAKING = 80
    SPEED_OTHER    = 400

    def __init__(self, master):
        self.master    = master
        self.running   = True
        self.state     = "warmup"
        self.frame_idx = 0
        self.messages  = []
        self.awake = False
        self.last_input_at = 0.0
        self._next_blink_at = time.monotonic() + self.BLINK_INTERVAL_SECONDS
        self._blink_until = 0.0

        # Thread -> main-thread command queue.
        # This is the ONLY correct way to drive Tkinter from a bg thread.
        self._q = queue.Queue()

        # ── Window setup ──────────────────────────────────────────────
        master.title("Pooh Terminal Demo")
        master.attributes("-fullscreen", True)
        master.configure(bg="#202040")
        master.bind("<Escape>", lambda e: self.shutdown())

        # Face display label (fills the whole window)
        self.bg_label = tk.Label(master, bg="#202040", bd=0)
        self.bg_label.place(x=0, y=0, width=self.BG_WIDTH, height=self.BG_HEIGHT)

        # Subtitle bar at the bottom — hidden when text is empty
        self.caption_var = tk.StringVar(value="")
        self.caption_label = tk.Label(
            master,
            textvariable=self.caption_var,
            bg="#000000",
            fg="#ffffff",
            font=("Courier", 16, "bold"),
            wraplength=760,
            justify=tk.LEFT,
            padx=14,
            pady=10,
        )
        # Start hidden; _apply_caption shows/hides it based on content

        # ── Load face images ──────────────────────────────────────────
        self.faces = self._load_faces()

        # ── Start main-thread loops ───────────────────────────────────
        self._poll_queue()   # drains _q every 40 ms
        self._animate()      # cycles face frames

        # Startup: play warmup animation then go to sleeping idle
        self._apply_state("warmup")
        self._apply_caption("Hello there, friend!")
        master.after(1800, lambda: self._apply_state("idle"))
        master.after(1900, lambda: self._apply_caption("Wake me up"))

        print("-" * 50, flush=True)
        print("  POOH DEMO  |  type here, face changes on screen", flush=True)
        print("-" * 50, flush=True)
        print("Hello there, friend!\n", flush=True)

        # Background thread owns stdin (SSH terminal)
        threading.Thread(target=self._input_loop, daemon=True).start()

    # ── Face loading ──────────────────────────────────────────────────

    def _load_faces(self):
        faces = {}
        for state in ("warmup", "idle", "listening", "thinking", "speaking", "error"):
            folder = os.path.join("faces", state)
            frames = []
            if os.path.isdir(folder):
                files = sorted(
                    f for f in os.listdir(folder) if f.lower().endswith(".png")
                )
                for fname in files:
                    img = Image.open(os.path.join(folder, fname)).resize(
                        (self.BG_WIDTH, self.BG_HEIGHT), Image.LANCZOS
                    )
                    frames.append(ImageTk.PhotoImage(img))
                print(f"  [{state}] {len(frames)} frame(s) loaded", flush=True)
            if not frames:
                blank = Image.new("RGB", (self.BG_WIDTH, self.BG_HEIGHT), "#202040")
                frames = [ImageTk.PhotoImage(blank)]
                print(f"  [{state}] no PNGs found -- blank placeholder", flush=True)
            faces[state] = frames
        return faces

    # ── Thread-safe API (call from any thread) ────────────────────────

    def set_state(self, new_state):
        """Queue a face-state change. Safe to call from the bg thread."""
        self._q.put(("state", new_state))

    def set_caption(self, text):
        """Queue a caption update. Safe to call from the bg thread."""
        self._q.put(("caption", text))

    # ── Main-thread-only methods ──────────────────────────────────────

    def _apply_state(self, new_state):
        """Apply state immediately. Must only be called from the main thread."""
        self.state = new_state
        self.frame_idx = 0

    def _apply_caption(self, text):
        """Apply caption immediately. Must only be called from the main thread."""
        self.caption_var.set(text)
        if text.strip():
            self.caption_label.place(relx=0.5, rely=0.88, anchor=tk.CENTER)
        else:
            self.caption_label.place_forget()

    def _poll_queue(self):
        """
        Drain the command queue every 40 ms in the main Tkinter thread.
        This is thread-safe -- no locking needed.
        """
        try:
            while True:
                cmd, value = self._q.get_nowait()
                if cmd == "state":
                    self._apply_state(value)
                elif cmd == "caption":
                    self._apply_caption(value)
                elif cmd == "reset_blink":
                    self._next_blink_at = time.monotonic() + self.BLINK_INTERVAL_SECONDS
                    self._blink_until = 0.0
        except queue.Empty:
            pass
        if self.running:
            self.master.after(40, self._poll_queue)

    def _animate(self):
        """Cycle through face frames in the main thread."""
        if not self.running:
            return

        frames = self.faces.get(self.state, self.faces["idle"])

        if self.state == "listening" and len(frames) > 1:
            # Awake and eyes open: blink every 45 s
            now = time.monotonic()
            if now >= self._next_blink_at:
                self._blink_until = now + self.BLINK_DURATION_SECONDS
                self._next_blink_at = now + self.BLINK_INTERVAL_SECONDS
            self.frame_idx = 1 if now < self._blink_until else 0

        elif self.state == "speaking" and len(frames) > 1:
            self.frame_idx = random.randint(0, len(frames) - 1)

        else:
            # idle (sleeping), thinking, warmup, error: cycle normally
            self.frame_idx = (self.frame_idx + 1) % len(frames)

        self.bg_label.config(image=frames[self.frame_idx])
        speed = self.SPEED_SPEAKING if self.state == "speaking" else self.SPEED_OTHER
        self.master.after(speed, self._animate)

    def _read_user_text(self, timeout_seconds=None):
        """
        Non-blocking stdin read with optional timeout.
        Returns: str (input) | None (EOF/interrupt) | "__TIMEOUT__" (timed out)
        """
        start = time.monotonic()
        while self.running:
            if timeout_seconds is not None and (time.monotonic() - start) >= timeout_seconds:
                return "__TIMEOUT__"
            try:
                ready, _, _ = select.select([sys.stdin], [], [], 0.5)
            except Exception:
                try:
                    line = input()
                except (EOFError, KeyboardInterrupt):
                    return None
                return (line or "").strip()
            if ready:
                line = sys.stdin.readline()
                if line == "":
                    return None
                return line.strip()
        return None

    # ── Background input / AI loop ────────────────────────────────────

    def _input_loop(self):
        awake_deadline = 0.0

        while self.running:
            now = time.monotonic()

            # ── 5-minute inactivity timeout: go back to sleep ─────────
            if self.awake and now >= awake_deadline:
                self.awake = False
                self.set_state("idle")
                self.set_caption("Wake me up")
                print("\n[FACE -> IDLE] session timeout, going to sleep", flush=True)

            # ── Set waiting face ──────────────────────────────────────
            if self.awake:
                self.set_state("listening")
                self.set_caption("")
            else:
                self.set_state("idle")   # sleeping face
                self.set_caption("Wake me up")

            print("\nYou: ", end="", flush=True)

            remaining = max(0.1, awake_deadline - time.monotonic()) if self.awake else None
            user_text = self._read_user_text(timeout_seconds=remaining)

            if user_text is None:
                self.shutdown()
                return
            if user_text == "__TIMEOUT__":
                continue   # expiration handled at top of loop
            if not user_text:
                continue
            if user_text.lower() in {"quit", "exit", "bye"}:
                self.set_caption("Goodbye!")
                print("\n[Pooh] Goodbye!", flush=True)
                time.sleep(1.0)
                self.shutdown()
                return

            # ── Wake up: play warmup animation on first input ─────────
            if not self.awake:
                print("[FACE -> WARMUP] waking up!", flush=True)
                self.set_state("warmup")
                self.set_caption("Oh! Hello there!")
                time.sleep(1.8)   # warmup animation plays
                # Reset blink clock so first blink is 45s from now
                self._q.put(("reset_blink", None))

            self.awake = True
            self.last_input_at = time.monotonic()
            awake_deadline = self.last_input_at + self.SESSION_TIMEOUT_SECONDS

            # ── Listening ────────────────────────────────────────────
            print("[FACE -> LISTENING]", flush=True)
            self.set_state("listening")
            self.set_caption("Listening...")
            time.sleep(0.4)

            # ── Thinking ─────────────────────────────────────────────
            print("[FACE -> THINKING]", flush=True)
            self.set_state("thinking")
            self.set_caption("Think, think, think...")

            try:
                answer = ask_ai(self.messages, user_text)
            except Exception as e:
                self.set_state("error")
                err = f"Oops: {e}"
                self.set_caption(err)
                print(f"[ERROR] {err}", flush=True)
                time.sleep(2.0)
                continue

            # ── Speaking ─────────────────────────────────────────────
            print("[FACE -> SPEAKING]", flush=True)
            self.set_state("speaking")

            # Speak via ElevenLabs in background (runs while typewriter plays)
            speak_elevenlabs(answer)

            pages = _paginate(answer)
            print("\n[Pooh] ", end="", flush=True)
            for p_idx, page in enumerate(pages):
                self.set_caption(page)
                # Type only the visible text chars (skip newlines in terminal)
                for ch in page:
                    if not self.running:
                        return
                    if ch != "\n":
                        print(ch, end="", flush=True)
                    time.sleep(0.04)
                # Pause between pages so user can read, then clear for next
                if p_idx < len(pages) - 1:
                    time.sleep(1.0)
                    self.set_caption("")
                    time.sleep(0.15)
                    print(" / ", end="", flush=True)
            print("\n", flush=True)

            # Back to awake listening
            time.sleep(0.5)
            self.set_state("listening")
            self.set_caption("")
            print("[FACE -> LISTENING] (awake)", flush=True)

    # ── Shutdown ──────────────────────────────────────────────────────

    def shutdown(self):
        if not self.running:
            return
        self.running = False
        try:
            self.master.destroy()
        except Exception:
            pass


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

def main():
    try:
        root = tk.Tk()
    except tk.TclError:
        # No display (SSH without DISPLAY=:0)
        run_terminal_only_demo()
        return

    TextFaceDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
