#!/bin/bash

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🤖 Pollo Assistant Setup Script${NC}"

# 1. Install System Dependencies
echo -e "${YELLOW}[1/3] Installing System Tools (apt)...${NC}"
sudo apt update
sudo apt install -y python3-tk libasound2-dev libportaudio2 cmake build-essential espeak-ng git

# 2. Create Folders
echo -e "${YELLOW}[2/3] Creating Folders...${NC}"
mkdir -p faces/idle
mkdir -p faces/listening
mkdir -p faces/thinking
mkdir -p faces/speaking
mkdir -p faces/error
mkdir -p faces/warmup

# 3. Install Python Libraries
echo -e "${YELLOW}[3/3] Installing Python Libraries...${NC}"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Download wake word model if missing
if [ ! -f "wakeword.onnx" ]; then
    echo -e "${YELLOW}Downloading default 'Hey Jarvis' wake word...${NC}"
    curl -L -o wakeword.onnx https://github.com/dscripka/openWakeWord/raw/main/openwakeword/resources/models/hey_jarvis_v0.1.onnx
fi

# Install whisper.cpp for transcription and 'Hey Pooh' wake fallback
if [ ! -d "whisper.cpp" ]; then
    echo -e "${YELLOW}Cloning whisper.cpp...${NC}"
    git clone --depth 1 https://github.com/ggerganov/whisper.cpp.git
fi

echo -e "${YELLOW}Building whisper.cpp...${NC}"
cmake -S whisper.cpp -B whisper.cpp/build
cmake --build whisper.cpp/build -j$(nproc 2>/dev/null || sysctl -n hw.logicalcpu 2>/dev/null || echo 4)

mkdir -p whisper.cpp/models
if [ ! -f "whisper.cpp/models/ggml-base.en.bin" ]; then
    echo -e "${YELLOW}Downloading Whisper base English model...${NC}"
    curl -L -o whisper.cpp/models/ggml-base.en.bin \
        https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin
fi

echo -e "${GREEN}✨ Setup Complete! Run 'source venv/bin/activate' then 'python main.py'${NC}"
