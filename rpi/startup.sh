#!/usr/bin/env bash

# Set working directory to the location of script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for missing dependencies
echo "Checking dependencies..."
REQUIRED_CMDS=("pactl" "bluetoothd" "pkill" "sudo")
MISSING=()
PY_MODULES=("dbus" "pyaudio" "numpy" "scipy" "pydantic")
MISSING_PY=()

for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING+=("$cmd")
    fi
done

# Check for Python modules used by Session_Config
for module in "${PY_MODULES[@]}"; do
    if ! python3 -c "import ${module}" 2>/dev/null; then
        MISSING_PY+=("${module}")
    fi
done

# Install dependencies only if any are missing
if [ ${#MISSING[@]} -gt 0 ] || [ ${#MISSING_PY[@]} -gt 0 ]; then
    if [ ${#MISSING[@]} -gt 0 ]; then
        echo "Missing system dependencies: ${MISSING[*]}"
    fi
    if [ ${#MISSING_PY[@]} -gt 0 ]; then
        echo "Missing Python modules: ${MISSING_PY[*]}"
    fi

    echo "Installing system dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        bluez \
        bluez-tools \
        dbus \
        python3-dbus \
        python3-numpy \
        python3-scipy \
        python3-pydantic \
        python3-pip \
        pulseaudio-utils \
        pipewire \
        procps \
        portaudio19-dev \
        python3-pyaudio

    
    # Verify installation
    echo "Verifying dependencies..."
    MISSING_AFTER=()
    MISSING_PY_AFTER=()
    for cmd in "${REQUIRED_CMDS[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            MISSING_AFTER+=("$cmd")
        fi
    done

    for module in "${PY_MODULES[@]}"; do
        if ! python3 -c "import ${module}" 2>/dev/null; then
            MISSING_PY_AFTER+=("${module}")
        fi
    done
    
    if [ ${#MISSING_AFTER[@]} -gt 0 ]; then
        echo "Error: Failed to install dependencies: ${MISSING_AFTER[*]}"
        exit 1
    fi

    if [ ${#MISSING_PY_AFTER[@]} -gt 0 ]; then
        echo "Error: Failed to install Python modules: ${MISSING_PY_AFTER[*]}"
        exit 1
    fi
else
    echo "All dependencies are already installed."
fi

# Ensure Bluetooth service is running
echo "Ensuring Bluetooth service is running..."
sudo systemctl start bluetooth

echo "Starting application..."
python3 main.py