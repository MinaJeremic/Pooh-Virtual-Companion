import tkinter as tk
from gui import BotGUI

if __name__ == "__main__":
    print("--- SYSTEM STARTING ---", flush=True)
    root = tk.Tk()
    app  = BotGUI(root)
    root.mainloop()
