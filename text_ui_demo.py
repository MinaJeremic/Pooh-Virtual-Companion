import threading
import time
import random
import tkinter as tk
from PIL import Image, ImageTk

from config import AI_CLIENT, CLAUDE_MODEL, SYSTEM_PROMPT


def ask_claude(messages, user_text):
    msgs = messages + [{"role": "user", "content": user_text}]
    response = AI_CLIENT.messages.create(
        model=CLAUDE_MODEL,
        system=SYSTEM_PROMPT,
        messages=msgs,
        max_tokens=300,
    )
    text = response.content[0].text.strip()
    messages.append({"role": "user", "content": user_text})
    messages.append({"role": "assistant", "content": text})
    return text


def run_terminal_only_demo():
    messages = []
    print("--- TERMINAL-ONLY POOH DEMO (no GUI display found) ---", flush=True)
    print("Type in terminal. Press Ctrl+C or type 'quit' to exit.\n", flush=True)
    print("Hello there, friend.", flush=True)

    while True:
        try:
            user_text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye for now.", flush=True)
            return

        if not user_text:
            continue
        if user_text.lower() in {"quit", "exit"}:
            print("Bye for now.", flush=True)
            return

        print("[STATE] LISTENING", flush=True)
        time.sleep(0.25)
        print("[STATE] THINKING", flush=True)

        try:
            answer = ask_claude(messages, user_text)
        except Exception as e:
            print(f"[ERROR] Claude error: {e}", flush=True)
            continue

        print("[STATE] SPEAKING", flush=True)
        print("[Pooh] ", end="", flush=True)
        for ch in answer:
            print(ch, end="", flush=True)
            time.sleep(0.018)
        print("", flush=True)
        print("[STATE] IDLE", flush=True)


class TextFaceDemo:
    BG_WIDTH, BG_HEIGHT = 800, 480

    def __init__(self, master):
        self.master = master
        self.master.title("Pooh Terminal Demo")
        self.master.attributes("-fullscreen", True)
        self.master.bind("<Escape>", lambda e: self.shutdown())

        self.state = "warmup"
        self.frame_idx = 0
        self.running = True
        self.messages = []

        self.background = tk.Label(master)
        self.background.place(x=0, y=0, width=self.BG_WIDTH, height=self.BG_HEIGHT)

        self.caption_var = tk.StringVar(value="")
        self.caption = tk.Label(
            master,
            textvariable=self.caption_var,
            bg="#000000",
            fg="#ffffff",
            font=("Arial", 18, "bold"),
            wraplength=760,
            justify=tk.CENTER,
            padx=10,
            pady=8,
        )
        self.caption.place(relx=0.5, rely=0.92, anchor=tk.CENTER)

        self.faces = self._load_faces()
        self._animate()

        print("--- TEXT-ONLY POOH DEMO ---", flush=True)
        print("Type in terminal. Press Ctrl+C or type 'quit' to exit.\n", flush=True)
        print("Hello there, friend.", flush=True)

        self.set_state("warmup")
        self.set_caption("Hello there, friend.")
        self.master.after(1500, lambda: self.set_state("idle"))

        threading.Thread(target=self._input_loop, daemon=True).start()

    def _load_faces(self):
        import os

        faces = {}
        states = ["warmup", "idle", "listening", "thinking", "speaking", "error"]

        for state in states:
            folder = os.path.join("faces", state)
            frames = []
            if os.path.isdir(folder):
                files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
                for file in files:
                    img = Image.open(os.path.join(folder, file)).resize((self.BG_WIDTH, self.BG_HEIGHT))
                    frames.append(ImageTk.PhotoImage(img))
            if not frames:
                blank = Image.new("RGB", (self.BG_WIDTH, self.BG_HEIGHT), "#202040")
                frames = [ImageTk.PhotoImage(blank)]
            faces[state] = frames

        return faces

    def set_state(self, new_state):
        def _set():
            self.state = new_state
            self.frame_idx = 0
        self.master.after(0, _set)

    def set_caption(self, text):
        self.master.after(0, lambda: self.caption_var.set(text))

    def _animate(self):
        if not self.running:
            return

        frames = self.faces.get(self.state, self.faces["idle"])

        if self.state == "speaking" and len(frames) > 1:
            self.frame_idx = random.randint(0, len(frames) - 1)
        else:
            self.frame_idx = (self.frame_idx + 1) % len(frames)

        self.background.config(image=frames[self.frame_idx])
        speed = 60 if self.state == "speaking" else 450
        self.master.after(speed, self._animate)

    def _ask_claude(self, user_text):
        return ask_claude(self.messages, user_text)

    def _type_print(self, text, delay=0.018):
        self.set_state("speaking")
        self.set_caption(text)
        print("[Pooh] ", end="", flush=True)
        for ch in text:
            if not self.running:
                return
            print(ch, end="", flush=True)
            time.sleep(delay)
        print("", flush=True)

    def _input_loop(self):
        while self.running:
            try:
                self.set_state("idle")
                self.set_caption("Waiting for your message in terminal...")
                user_text = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                self.shutdown()
                return

            if not user_text:
                continue
            if user_text.lower() in {"quit", "exit"}:
                self.shutdown()
                return

            self.set_state("listening")
            self.set_caption("Listening...")
            time.sleep(0.35)

            self.set_state("thinking")
            self.set_caption("Think, think, think...")

            try:
                answer = self._ask_claude(user_text)
            except Exception as e:
                self.set_state("error")
                err = f"Claude error: {e}"
                self.set_caption(err)
                print(f"\n[ERROR] {err}", flush=True)
                time.sleep(1.2)
                continue

            self._type_print(answer)
            self.set_state("idle")
            self.set_caption("Waiting for your message in terminal...")

    def shutdown(self):
        if not self.running:
            return
        self.running = False
        try:
            self.master.destroy()
        except Exception:
            pass


def main():
    try:
        root = tk.Tk()
    except tk.TclError:
        run_terminal_only_demo()
        return

    TextFaceDemo(root)
    root.mainloop()


if __name__ == "__main__":
    main()
