"""Quick face test — cycles through every state so you can preview on the Pi display."""

import time
import tkinter as tk
from PIL import Image, ImageTk
import os

BG_WIDTH, BG_HEIGHT = 800, 480
STATES = ["warmup", "idle", "listening", "thinking", "speaking", "error", "capturing"]
SECONDS_PER_FRAME = 2


def load_all_frames():
    frames = {}
    for state in STATES:
        folder = os.path.join("faces", state)
        frames[state] = []
        if os.path.exists(folder):
            files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".png"))
            for f in files:
                img = Image.open(os.path.join(folder, f)).resize((BG_WIDTH, BG_HEIGHT))
                frames[state].append(ImageTk.PhotoImage(img))
    return frames


def main():
    root = tk.Tk()
    root.title("Face Test")
    root.attributes("-fullscreen", True)
    root.bind("<Escape>", lambda e: root.destroy())

    label = tk.Label(root, bg="black")
    label.place(x=0, y=0, width=BG_WIDTH, height=BG_HEIGHT)

    info = tk.Label(root, text="", font=("Arial", 24), fg="white", bg="black")
    info.place(relx=0.5, rely=0.95, anchor=tk.S)

    frames = load_all_frames()

    sequence = []
    for state in STATES:
        if frames[state]:
            for i, frame in enumerate(frames[state]):
                sequence.append((state, i, frame))
        else:
            print(f"[SKIP] No images for '{state}'")

    if not sequence:
        print("No face images found! Put PNGs in faces/<state>/ folders.")
        return

    idx = [0]

    def show_next():
        state, frame_num, img = sequence[idx[0]]
        label.config(image=img)
        info.config(text=f"{state} (frame {frame_num + 1}/{len(frames[state])})")
        idx[0] = (idx[0] + 1) % len(sequence)
        root.after(SECONDS_PER_FRAME * 1000, show_next)

    print(f"Showing {len(sequence)} frames across {len([s for s in STATES if frames[s]])} states")
    print("Press Escape to exit")
    show_next()
    root.mainloop()


if __name__ == "__main__":
    main()
