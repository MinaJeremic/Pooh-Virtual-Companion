import os
import subprocess

WHISPER_MODEL = "./whisper.cpp/models/ggml-base.en.bin"
WHISPER_CLI_CANDIDATES = [
    "./whisper.cpp/build/bin/whisper-cli",
    "./whisper.cpp/build/bin/main",
    "./whisper.cpp/main",
]
WAKE_PHRASES = ["hey pooh", "hey poo", "hey puh", "hey po", "hey boo", "hey poooh"]
WAKE_LISTEN_CHUNK = 2.0
WAKE_MIN_PEAK = 0.005  # Lowered for quiet Pi mics — AGC normalises level before Whisper


def get_whisper_cli_path():
    for path in WHISPER_CLI_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def whisper_ready():
    return bool(get_whisper_cli_path() and os.path.exists(WHISPER_MODEL))


def parse_whisper_output(stdout):
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        return ""
    last = lines[-1]
    return last.split("]", 1)[1].strip() if "]" in last else last


def transcribe_file(filename, timeout=20):
    cli_path = get_whisper_cli_path()
    if not cli_path:
        print("[ERROR] whisper.cpp binary not found.", flush=True)
        return ""

    if not os.path.exists(WHISPER_MODEL):
        print(f"[ERROR] Whisper model not found: {WHISPER_MODEL}", flush=True)
        return ""

    try:
        result = subprocess.run(
            [cli_path, "-m", WHISPER_MODEL, "-l", "en", "-t", "4", "--no-prints", "-f", filename],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return parse_whisper_output(result.stdout).strip()
    except Exception as e:
        print(f"[TRANSCRIBE ERROR] {e}", flush=True)
        return ""
