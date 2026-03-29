import os
import queue
import random
import threading
import time
import tkinter as tk

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

    # Face animation speeds (ms per frame)
    SPEED_SPEAKING = 80
    SPEED_OTHER    = 400

    def __init__(self, master):
        self.master    = master
        self.running   = True
        self.state     = "warmup"
        self.frame_idx = 0
        self.messages  = []

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

        # Subtitle bar at the bottom
        self.caption_var = tk.StringVar(value="")
        tk.Label(
            master,
            textvariable=self.caption_var,
            bg="#000000",
            fg="#ffffff",
            font=("Arial", 20, "bold"),
            wraplength=780,
            justify=tk.CENTER,
            padx=12,
            pady=10,
        ).place(relx=0.5, rely=0.92, anchor=tk.CENTER)

        # ── Load face images ──────────────────────────────────────────
        self.faces = self._load_faces()

        # ── Start main-thread loops ───────────────────────────────────
        self._poll_queue()   # drains _q every 40 ms
        self._animate()      # cycles face frames

        # Warmup greeting then settle to idle
        self._apply_state("warmup")
        self._apply_caption("Hello there, friend!")
        master.after(1600, lambda: self._apply_state("idle"))
        master.after(1700, lambda: self._apply_caption("Type in your SSH terminal..."))

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
        except queue.Empty:
            pass
        if self.running:
            self.master.after(40, self._poll_queue)

    def _animate(self):
        """Cycle through face frames in the main thread."""
        if not self.running:
            return
        frames = self.faces.get(self.state, self.faces["idle"])
        if self.state == "speaking" and len(frames) > 1:
            self.frame_idx = random.randint(0, len(frames) - 1)
        else:
            self.frame_idx = (self.frame_idx + 1) % len(frames)
        self.bg_label.config(image=frames[self.frame_idx])
        speed = self.SPEED_SPEAKING if self.state == "speaking" else self.SPEED_OTHER
        self.master.after(speed, self._animate)

    # ── Background input / AI loop ────────────────────────────────────

    def _input_loop(self):
        while self.running:
            # ── Idle: wait for the user to type ──────────────────────
            self.set_state("idle")
            self.set_caption("Type in your SSH terminal...")
            print("\nYou: ", end="", flush=True)

            try:
                user_text = input().strip()
            except (EOFError, KeyboardInterrupt):
                self.shutdown()
                return

            if not user_text:
                continue
            if user_text.lower() in {"quit", "exit", "bye"}:
                self.set_caption("Goodbye!")
                print("\n[Pooh] Goodbye!", flush=True)
                time.sleep(1.0)
                self.shutdown()
                return

            # ── Listening ────────────────────────────────────────────
            print("[FACE -> LISTENING]", flush=True)
            self.set_state("listening")
            self.set_caption("Listening...")
            time.sleep(0.5)   # hold listening face so it's visible

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
            self.set_caption(answer)

            print("\n[Pooh] ", end="", flush=True)
            for ch in answer:
                if not self.running:
                    return
                print(ch, end="", flush=True)
                time.sleep(0.018)
            print("\n", flush=True)

            # Brief pause on speaking face before looping back to idle
            time.sleep(0.6)
            print("[FACE -> IDLE]", flush=True)

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
