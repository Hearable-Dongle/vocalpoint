#!/usr/bin/env bash

# Set working directory to the location of script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check for missing dependencies
echo "Checking dependencies..."
REQUIRED_CMDS=("pactl" "pw-loopback" "bluetoothctl" "pkill" "sudo")
MISSING=()

for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &> /dev/null; then
        MISSING+=("$cmd")
    fi
done

# Install dependencies only if any are missing
if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing dependencies: ${MISSING[*]}"
    echo "Installing system dependencies..."
    sudo apt-get update
    sudo apt-get install -y \
        bluez \
        pulseaudio-utils \
        pipewire \
        procps
    
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

echo "All dependencies installed successfully. Starting application..."
python3 main.py