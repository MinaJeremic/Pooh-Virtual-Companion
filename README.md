# Pooh-Virtual-Companion

## Wake word behavior

- If `wakeword.onnx` is present, the app uses the ONNX wake-word detector.
- If the ONNX model is missing but `whisper.cpp` is installed, the app now falls back to Whisper-based phrase detection for `Hey Pooh`.
- If neither is available, the app falls back to push-to-talk.

## Quick setup

Run the setup script:

`./setup.sh`

That installs Python packages, builds `whisper.cpp`, and downloads the English base Whisper model.

It does not auto-download the default `Hey Jarvis` ONNX model, so `Hey Pooh` uses the Whisper fallback by default.

## Run

Start the assistant with:

`python main.py`

Then say `Hey Pooh`.
