import re
import json
import time
import base64
import random
import threading

from config import AI_CLIENT, CLAUDE_MODEL, SYSTEM_PROMPT, CURRENT_CONFIG, BotStates
from actions import execute_action, capture_image


class Brain:
    """
    Handles all Claude interactions, action routing, and proactive check-ins.

    Callbacks expected:
        set_state(state, msg, cam_path=None)
        append_text(text, newline=True)
        stream_text(chunk)
        get_state() -> str
    """

    def __init__(self, tts_engine, interrupted_event, callbacks):
        self.tts         = tts_engine
        self.interrupted = interrupted_event
        self.cb          = callbacks          # dict of callables
        self.session_memory   = []
        self.permanent_memory = []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_state(self, state, msg="", cam_path=None):
        self.cb["set_state"](state, msg, cam_path)

    def _append_text(self, text, newline=True):
        self.cb["append_text"](text, newline)

    def _stream_text(self, chunk):
        self.cb["stream_text"](chunk)

    def _get_state(self):
        return self.cb["get_state"]()

    @staticmethod
    def _extract_json(text):
        try:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            return json.loads(match.group(0)) if match else None
        except:
            return None

    def _speak_fallback(self, text, img_path):
        self._set_state(BotStates.SPEAKING, "Speaking...", img_path)
        self._append_text("BOT: ", newline=False)
        self._append_text(text, newline=True)
        self.tts.enqueue(text)

    # ── Main response ─────────────────────────────────────────────────────────

    def chat_and_respond(self, text, img_path=None):
        if "forget everything" in text.lower() or "reset memory" in text.lower():
            self.session_memory   = []
            self.permanent_memory = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.tts.enqueue("Okay. Memory wiped.")
            self._set_state(BotStates.IDLE, "Memory Wiped")
            return

        self._set_state(BotStates.THINKING, "Thinking...", img_path)

        user_msg    = {"role": "user", "content": text}
        messages    = self.permanent_memory + self.session_memory + [user_msg]
        api_messages = self._build_api_messages(messages, text, img_path)

        self.tts.start_thinking_sounds()

        full_response = ""
        sentence_buf  = ""
        is_action     = False

        try:
            with AI_CLIENT.messages.stream(
                model=CLAUDE_MODEL,
                system=SYSTEM_PROMPT,
                messages=api_messages,
                max_tokens=512,
            ) as stream:
                for chunk in stream.text_stream:
                    if self.interrupted.is_set():
                        break

                    full_response += chunk

                    if '{"' in chunk or "action:" in chunk.lower():
                        is_action = True
                        self.tts.stop_thinking_sounds()
                        continue

                    if is_action:
                        continue

                    self.tts.stop_thinking_sounds()
                    if self._get_state() != BotStates.SPEAKING:
                        self._set_state(BotStates.SPEAKING, "Speaking...", img_path)
                        self._append_text("BOT: ", newline=False)

                    self._stream_text(chunk)
                    sentence_buf += chunk

                    if any(p in chunk for p in ".!?\n"):
                        clean = sentence_buf.strip()
                        if clean and re.search(r"[a-zA-Z0-9]", clean):
                            self.tts.enqueue(clean)
                        sentence_buf = ""

            # Handle remaining sentence fragment
            if not is_action and sentence_buf.strip():
                self.tts.enqueue(sentence_buf.strip())

            if is_action:
                self._handle_action(full_response, text, img_path)
            else:
                self._append_text("")
                self.session_memory.append({"role": "assistant", "content": full_response})

            self.tts.wait_for_completion()
            self._set_state(BotStates.IDLE, "Ready")

        except Exception as e:
            print(f"LLM Error: {e}")
            self._set_state(BotStates.ERROR, "Brain Freeze!")

    def _build_api_messages(self, messages, text, img_path):
        if img_path:
            with open(img_path, "rb") as f:
                img_data = base64.standard_b64encode(f.read()).decode("utf-8")
            return [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_data}},
                {"type": "text", "text": text},
            ]}]
        return [m for m in messages if m.get("role") != "system"]

    def _handle_action(self, full_response, original_text, img_path):
        self.tts.stop_thinking_sounds()
        action_data = self._extract_json(full_response)
        if not action_data:
            return

        result = execute_action(action_data)

        if result and result.startswith("CHAT_FALLBACK::"):
            chat_text = result.split("::", 1)[1]
            self._speak_fallback(chat_text, img_path)
            self.session_memory.append({"role": "assistant", "content": chat_text})
            self.tts.wait_for_completion()
            self._set_state(BotStates.IDLE, "Ready")
            return

        if result == "IMAGE_CAPTURE_TRIGGERED":
            new_path = capture_image()
            if new_path:
                self.chat_and_respond(original_text, img_path=new_path)
            return

        if result == "INVALID_ACTION":
            self._speak_fallback("I am not sure how to do that.", img_path)
        elif result == "SEARCH_EMPTY":
            self._speak_fallback("I searched, but I couldn't find any news about that.", img_path)
        elif result == "SEARCH_ERROR":
            self._speak_fallback("I cannot reach the internet right now.", img_path)
        elif result:
            self._set_state(BotStates.THINKING, "Reading...")
            self.tts.start_thinking_sounds()
            summary = AI_CLIENT.messages.create(
                model=CLAUDE_MODEL,
                system="Summarize this result in one short, friendly sentence.",
                messages=[{"role": "user", "content": f"RESULT: {result}\nUser Question: {original_text}"}],
                max_tokens=100,
            )
            final_text = summary.content[0].text
            self.tts.stop_thinking_sounds()
            self._set_state(BotStates.SPEAKING, "Speaking...", img_path)
            self._append_text("BOT: ", newline=False)
            self._append_text(final_text, newline=True)
            self.tts.enqueue(final_text)
            self.session_memory.append({"role": "assistant", "content": final_text})

    # ── Proactive check-in ────────────────────────────────────────────────────

    def start_proactive_checkin(self):
        threading.Thread(target=self._checkin_loop, daemon=True).start()

    def _checkin_loop(self):
        interval = CURRENT_CONFIG.get("proactive_checkin_minutes", 30)
        if interval <= 0:
            return
        time.sleep(60)
        while True:
            time.sleep(interval * 60)
            if self._get_state() == BotStates.IDLE and not self.interrupted.is_set():
                print("[PROACTIVE] Triggering check-in...", flush=True)
                prompt = random.choice([
                    "Check in on the user warmly. Ask how they are doing. Keep it to one short sentence.",
                    "Say something encouraging or kind to the user. One sentence only.",
                    "Gently remind the user you are here if they need to talk. One short sentence.",
                ])
                try:
                    resp = AI_CLIENT.messages.create(
                        model=CLAUDE_MODEL,
                        system=SYSTEM_PROMPT,
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=60,
                    )
                    checkin_text = resp.content[0].text.strip()
                    self._set_state(BotStates.SPEAKING, "Checking in...")
                    self.tts.enqueue(checkin_text)
                    self._append_text(f"BOT: {checkin_text}")
                    self.tts.wait_for_completion()
                    self._set_state(BotStates.IDLE, "Waiting...")
                except Exception as e:
                    print(f"[PROACTIVE] Error: {e}", flush=True)
