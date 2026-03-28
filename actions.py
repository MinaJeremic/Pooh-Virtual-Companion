import datetime
import subprocess

from PIL import Image
from ddgs import DDGS

from config import CURRENT_CONFIG, IMAGE_FILE


VALID_TOOLS = {"get_time", "search_web", "capture_image"}

ALIASES = {
    "google":      "search_web",
    "browser":     "search_web",
    "news":        "search_web",
    "search_news": "search_web",
    "look":        "capture_image",
    "see":         "capture_image",
    "check_time":  "get_time",
}


def execute_action(action_data):
    """
    Route an action dict to the correct handler.
    Returns a result string or a sentinel like 'INVALID_ACTION', 'SEARCH_EMPTY', etc.
    """
    raw_action = action_data.get("action", "").lower().strip()
    value      = action_data.get("value") or action_data.get("query")
    action     = ALIASES.get(raw_action, raw_action)

    print(f"ACTION: {raw_action} -> {action}", flush=True)

    if action not in VALID_TOOLS:
        if value and isinstance(value, str) and len(value.split()) > 1:
            return f"CHAT_FALLBACK::{value}"
        return "INVALID_ACTION"

    if action == "get_time":
        return f"The current time is {datetime.datetime.now().strftime('%I:%M %p')}."

    if action == "search_web":
        return _search_web(value)

    if action == "capture_image":
        return "IMAGE_CAPTURE_TRIGGERED"

    return None


def _search_web(query):
    print(f"Searching web for: {query}...", flush=True)
    try:
        with DDGS() as ddgs:
            results = []

            try:
                results = list(ddgs.news(query, region="us-en", max_results=1))
                if results:
                    print(f"[SEARCH] News: {results[0].get('title')}", flush=True)
            except Exception as e:
                print(f"[SEARCH] News error: {e}", flush=True)

            if not results:
                try:
                    results = list(ddgs.text(query, region="us-en", max_results=1))
                    if results:
                        print(f"[SEARCH] Text: {results[0].get('title')}", flush=True)
                except Exception as e:
                    print(f"[SEARCH] Text error: {e}", flush=True)

            if results:
                r     = results[0]
                title = r.get("title", "No Title")
                body  = r.get("body", r.get("snippet", "No Body"))
                return f"SEARCH RESULTS for '{query}':\nTitle: {title}\nSnippet: {body[:300]}"
            else:
                return "SEARCH_EMPTY"

    except Exception as e:
        print(f"[SEARCH] Connection error: {e}", flush=True)
        return "SEARCH_ERROR"


def capture_image():
    """Take a photo with the Pi camera and return the file path, or None on failure."""
    try:
        subprocess.run(
            ["rpicam-still", "-t", "500", "-n",
             "--width", "640", "--height", "480", "-o", IMAGE_FILE],
            check=True,
        )
        rotation = CURRENT_CONFIG.get("camera_rotation", 0)
        if rotation != 0:
            img = Image.open(IMAGE_FILE)
            img = img.rotate(rotation, expand=True)
            img.save(IMAGE_FILE)
        return IMAGE_FILE
    except Exception as e:
        print(f"Camera Error: {e}")
        return None
