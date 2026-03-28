import sys
import time
import atexit
import threading
import subprocess

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk

from config import BotStates, CURRENT_CONFIG
from memory import load_chat_history, save_chat_history
from audio import record_voice_adaptive, record_voice_ptt
from wakeword import WakeWordDetector
from voice import TTSEngine
from brain import Brain


class BotGUI:
    BG_WIDTH,      BG_HEIGHT      = 800, 480
    OVERLAY_WIDTH, OVERLAY_HEIGHT = 400, 300

    def __init__(self, master):
        self.master        = master
        self.current_state = BotStates.WARMUP
        self.current_volume = 0
        self.animations    = {}
        self.current_frame_index   = 0
        self.current_overlay_image = None

        # ── Events ──────────────────────────────────────────────────────────
        self.ptt_event        = threading.Event()
        self.recording_active = threading.Event()
        self.interrupted      = threading.Event()

        # ── Core systems ────────────────────────────────────────────────────
        self.tts        = TTSEngine(self.interrupted)
        self.detector   = WakeWordDetector()
        self.brain      = Brain(
            tts_engine=self.tts,
            interrupted_event=self.interrupted,
            callbacks={
                "set_state":   self.set_state,
                "append_text": self.append_to_text,
                "stream_text": self._stream_to_text,
                "get_state":   lambda: self.current_state,
            },
        )

        # ── Memory ──────────────────────────────────────────────────────────
        self.brain.permanent_memory = load_chat_history()
        self.brain.session_memory   = []

        # ── Window & bindings ────────────────────────────────────────────────
        master.title("Pooh Assistant")
        master.attributes("-fullscreen", True)
        master.bind("<Escape>",  self.exit_fullscreen)
        master.bind("<Return>",  self.handle_ptt_toggle)
        master.bind("<space>",   self.handle_speaking_interrupt)
        atexit.register(self.safe_exit)
        self.last_ptt_time = 0

        # ── GUI widgets ──────────────────────────────────────────────────────
        self.background_label = tk.Label(master)
        self.background_label.place(x=0, y=0, width=self.BG_WIDTH, height=self.BG_HEIGHT)
        self.background_label.bind("<Button-1>", self.toggle_hud_visibility)

        self.overlay_label = tk.Label(master, bg="black")
        self.overlay_label.bind("<Button-1>", self.toggle_hud_visibility)

        self.response_text = tk.Text(
            master, height=6, width=60, wrap=tk.WORD,
            state=tk.DISABLED, bg="#ffffff", fg="#000000", font=("Arial", 12),
        )

        self.status_var   = tk.StringVar(value="Initializing...")
        self.status_label = ttk.Label(master, textvariable=self.status_var,
                                      background="#2e2e2e", foreground="white")
        self.exit_button  = ttk.Button(master, text="Exit & Save", command=self.safe_exit)

        self.load_animations()
        self.update_animation()

        # ── Start background threads ─────────────────────────────────────────
        threading.Thread(target=self._main_loop, daemon=True).start()
        self.brain.start_proactive_checkin()

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def safe_exit(self):
        print("\n--- SHUTDOWN ---", flush=True)
        self.tts.stop_current()
        self.recording_active.clear()
        save_chat_history(self.brain.permanent_memory, self.brain.session_memory)
        self.master.quit()
        sys.exit(0)

    def exit_fullscreen(self, event=None):
        self.master.attributes("-fullscreen", False)
        self.safe_exit()

    # ── Input handlers ────────────────────────────────────────────────────────

    def handle_ptt_toggle(self, event=None):
        now = time.time()
        if now - self.last_ptt_time < 0.5:
            return
        self.last_ptt_time = now

        if self.recording_active.is_set():
            print("[PTT] Toggle OFF", flush=True)
            self.recording_active.clear()
        elif self.current_state == BotStates.IDLE or "Wait" in self.status_var.get():
            print("[PTT] Toggle ON", flush=True)
            self.recording_active.set()
            self.ptt_event.set()

    def handle_speaking_interrupt(self, event=None):
        if self.current_state in (BotStates.SPEAKING, BotStates.THINKING):
            self.interrupted.set()
            self.tts.stop_current()
            self.set_state(BotStates.IDLE, "Interrupted.")

    # ── HUD ───────────────────────────────────────────────────────────────────

    def toggle_hud_visibility(self, event=None):
        try:
            if self.response_text.winfo_ismapped():
                self.response_text.place_forget()
                self.status_label.place_forget()
                self.exit_button.place_forget()
            else:
                self.response_text.place(relx=0.5, rely=0.82, anchor=tk.S)
                self.status_label.place(relx=0.5, rely=1.0, anchor=tk.S, relwidth=1)
                self.exit_button.place(x=10, y=10)
        except tk.TclError:
            pass

    # ── State & text ──────────────────────────────────────────────────────────

    def set_state(self, state, msg="", cam_path=None):
        def _update():
            if msg:
                print(f"[STATE] {state.upper()}: {msg}", flush=True)
            if self.current_state != state:
                self.current_state       = state
                self.current_frame_index = 0
            if msg:
                self.status_var.set(msg)
            if cam_path and state in (BotStates.THINKING, BotStates.SPEAKING):
                try:
                    import os
                    if os.path.exists(cam_path):
                        img = Image.open(cam_path).resize((self.OVERLAY_WIDTH, self.OVERLAY_HEIGHT))
                        self.current_overlay_image = ImageTk.PhotoImage(img)
                        self.overlay_label.config(image=self.current_overlay_image)
                        self.overlay_label.place(x=200, y=90)
                        return
                except:
                    pass
            self.overlay_label.place_forget()
        self.master.after(0, _update)

    def append_to_text(self, text, newline=True):
        def _update():
            self.response_text.config(state=tk.NORMAL)
            self.response_text.insert(tk.END, text + ("\n" if newline else ""))
            self.response_text.see(tk.END)
            self.response_text.config(state=tk.DISABLED)
        self.master.after(0, _update)

    def _stream_to_text(self, chunk):
        def _update():
            self.response_text.config(state=tk.NORMAL)
            self.response_text.insert(tk.END, chunk)
            self.response_text.see(tk.END)
            self.response_text.config(state=tk.DISABLED)
        self.master.after(0, _update)

    # ── Animation ─────────────────────────────────────────────────────────────

    def load_animations(self):
        import os, random
        base_path = "faces"
        states    = [s for s in vars(BotStates) if not s.startswith("_")]
        state_vals = [getattr(BotStates, s) for s in states]

        for state in state_vals:
            folder = os.path.join(base_path, state)
            self.animations[state] = []
            if os.path.exists(folder):
                files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
                for f in files:
                    img = Image.open(os.path.join(folder, f)).resize((self.BG_WIDTH, self.BG_HEIGHT))
                    self.animations[state].append(ImageTk.PhotoImage(img))
            if not self.animations[state]:
                blank = Image.new("RGB", (self.BG_WIDTH, self.BG_HEIGHT), "#0000FF")
                self.animations[state].append(ImageTk.PhotoImage(blank))

    def update_animation(self):
        import random
        frames = self.animations.get(self.current_state) or self.animations.get(BotStates.IDLE, [])
        if not frames:
            self.master.after(500, self.update_animation)
            return

        if self.current_state == BotStates.SPEAKING and len(frames) > 1:
            self.current_frame_index = random.randint(1, len(frames) - 1)
        else:
            self.current_frame_index = (self.current_frame_index + 1) % len(frames)

        self.background_label.config(image=frames[self.current_frame_index])
        speed = 50 if self.current_state == BotStates.SPEAKING else 500
        self.master.after(speed, self.update_animation)

    # ── Main loop ─────────────────────────────────────────────────────────────

    def _main_loop(self):
        try:
            self._warm_up()
            self.tts.start()

            while True:
                trigger = self.detector.detect(self.ptt_event)

                if self.interrupted.is_set():
                    self.interrupted.clear()
                    self.set_state(BotStates.IDLE, "Resetting...")
                    continue

                self.set_state(BotStates.LISTENING, "I'm listening!")

                if trigger == "PTT":
                    audio_file = record_voice_ptt(self.recording_active)
                else:
                    audio_file = record_voice_adaptive()

                if not audio_file:
                    self.set_state(BotStates.IDLE, "Heard nothing.")
                    continue

                user_text = self._transcribe(audio_file)
                if not user_text:
                    self.set_state(BotStates.IDLE, "Transcription empty.")
                    continue

                self.append_to_text(f"YOU: {user_text}")
                self.interrupted.clear()
                self.brain.chat_and_respond(user_text)

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.set_state(BotStates.ERROR, f"Fatal Error: {str(e)[:40]}")

    def _warm_up(self):
        self.set_state(BotStates.WARMUP, "Warming up brains...")
        from config import CLAUDE_MODEL
        print(f"Using Claude model: {CLAUDE_MODEL}", flush=True)
        self.tts.enqueue("Hello there, friend.")
        print("Ready.", flush=True)

    def _transcribe(self, filename):
        print("Transcribing...", flush=True)
        try:
            result = subprocess.run(
                ["./whisper.cpp/build/bin/whisper-cli",
                 "-m", "./whisper.cpp/models/ggml-base.en.bin",
                 "-l", "en", "-t", "4", "-f", filename],
                capture_output=True, text=True,
            )
            lines = result.stdout.strip().split("\n")
            if lines and lines[-1].strip():
                last = lines[-1].strip()
                transcription = last.split("]")[1].strip() if "]" in last else last
            else:
                transcription = ""
            print(f"Heard: '{transcription}'", flush=True)
            return transcription.strip()
        except Exception as e:
            print(f"Transcription Error: {e}")
            return ""
