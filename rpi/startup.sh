#!/usr/bin/env bash

# Set working directory to the location of script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for missing dependencies
echo "Checking dependencies..."
REQUIRED_CMDS=("pactl" "bluetoothd" "pkill" "sudo")
MISSING=()

for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING+=("$cmd")
    fi
done

# Check for Python modules
if ! python3 -c "import dbus" 2>/dev/null; then
    MISSING+=("python3-dbus")
fi
if ! python3 -c "import pyaudio" 2>/dev/null; then
    MISSING+=("python3-pyaudio")
fi

# Install dependencies only if any are missing
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing dependencies: ${MISSING[*]}"
    echo "Installing system dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        bluez \
        bluez-tools \
        dbus \
        python3-dbus \
        pulseaudio-utils \
        pipewire \
        procps \
        portaudio19-dev \
        python3-pyaudio
    
    # Verify installation
    echo "Verifying dependencies..."
    MISSING_AFTER=()
    for cmd in "${REQUIRED_CMDS[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            MISSING_AFTER+=("$cmd")
        fi
    done
    
    if [ ${#MISSING_AFTER[@]} -gt 0 ]; then
        echo "Error: Failed to install dependencies: ${MISSING_AFTER[*]}"
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