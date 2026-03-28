import json
import os
from config import MEMORY_FILE, SYSTEM_PROMPT


def load_chat_history():
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return [{"role": "system", "content": SYSTEM_PROMPT}]


def save_chat_history(permanent_memory, session_memory):
    full = permanent_memory + session_memory
    conv = full[1:]
    if len(conv) > 10:
        conv = conv[-10:]
    with open(MEMORY_FILE, "w") as f:
        json.dump([full[0]] + conv, f, indent=4)
