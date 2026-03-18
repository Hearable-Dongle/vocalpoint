#!/usr/bin/env python3
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "mic2airpods"
CONFIG_PATH = CONFIG_DIR / "config.json"
SERVICE_DIR = Path.home() / ".config" / "systemd" / "user"
SERVICE_PATH = SERVICE_DIR / "mic2airpods.service"

MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def run(cmd, check=True, capture=False, text=True, input_data=None):
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=text,
        input=input_data,
    )


def have(cmd):
    return shutil.which(cmd) is not None


def ensure_deps():
    missing = [c for c in ["bluetoothctl", "pactl", "pw-loopback", "systemctl"] if not have(c)]
    if missing:
        print("Missing required commands:", ", ".join(missing))
        print("Install PipeWire/BlueZ tools first (see prereqs).")
        sys.exit(1)


def bluetoothctl(commands, timeout=None):
    """
    Run bluetoothctl in batch mode.
    """
    input_data = "\n".join(commands) + "\nquit\n"
    result = subprocess.run(
        ["bluetoothctl"],
        input=input_data,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return result.stdout + ("\n" + result.stderr if result.stderr else "")


def wait_for_bluetoothd(timeout=15):
    start = time.time()
    while time.time() - start < timeout:
        r = run(["systemctl", "is-active", "bluetooth"], check=False, capture=True)
        if r.stdout.strip() == "active":
            return True
        time.sleep(0.5)
    return False


def restart_bluetooth_service():
    """
    Try restarting bluetoothd. If sudo is unavailable/non-interactive, fall back gracefully.
    """
    print("Restarting Bluetooth service...")
    if have("sudo"):
        subprocess.run(
            ["sudo", "-n", "systemctl", "restart", "bluetooth"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["systemctl", "restart", "bluetooth"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    time.sleep(2)


def scan_for_device(mac, scan_seconds=15):
    """
    Scan for devices and verify the requested MAC shows up.
    """
    print(f"Scanning for AirPods for up to {scan_seconds} seconds...")
    print("Make sure the case is open and the pairing light is flashing white.")

    p = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    found = False
    collected = []

    try:
        for cmd in ["power on", "scan on"]:
            p.stdin.write(cmd + "\n")
            p.stdin.flush()
            time.sleep(0.5)

        start = time.time()
        while time.time() - start < scan_seconds:
            line = p.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue

            line = line.rstrip()
            collected.append(line)
            print(line)

            if mac.upper() in line.upper():
                found = True
                break

        try:
            p.stdin.write("scan off\n")
            p.stdin.write("quit\n")
            p.stdin.flush()
        except Exception:
            pass

    finally:
        try:
            p.terminate()
        except Exception:
            pass

    if found:
        return True

    # Fallback: check known devices list after scan
    devices = run(["bluetoothctl", "devices"], check=False, capture=True)
    if mac.upper() in devices.stdout.upper():
        return True

    print("\nScan finished, but device was not found.")
    if collected:
        print("\nRecent bluetoothctl output:")
        for line in collected[-20:]:
            print(line)
    return False


def list_sources():
    r = run(["pactl", "list", "sources", "short"], capture=True)
    sources = []
    for line in r.stdout.strip().splitlines():
        parts = line.split()
        if len(parts) >= 2:
            idx = parts[0]
            name = parts[1]
            sources.append((idx, name, line))
    return sources


def choose_mic_source():
    sources = list_sources()

    print("\nRaw pactl sources:")
    if sources:
        for idx, name, raw in sources:
            print(f"  {raw}")
    else:
        print("  (none)")

    if not sources:
        print("\nNo sources found via pactl.")
        print("Make sure:")
        print("  1. your mic array is plugged in")
        print("  2. PipeWire is running")
        print("  3. the mic appears in: arecord -l")
        sys.exit(1)

    print("\nAudio input sources found:")
    filtered = []
    for idx, name, raw in sources:
        if ".monitor" in name:
            continue
        if name.startswith("bluez_input."):
            continue
        filtered.append((idx, name, raw))

    if not filtered:
        print("No suitable non-Bluetooth sources found in pactl.")
        print("\nRun these commands and check whether your mic is visible:")
        print("  arecord -l")
        print("  pactl list sources short")
        print("  lsusb")
        sys.exit(1)

    for n, (idx, name, raw) in enumerate(filtered, 1):
        print(f"  [{n}] {name}")

    while True:
        choice = input("Select the mic array source number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(filtered):
            return filtered[int(choice) - 1][1]
        print("Invalid selection. Try again.")


def validate_mac(mac):
    return bool(MAC_RE.match(mac))


def write_config(mac, mic_source, latency_frames=128, rate=48000, profile="headset-head-unit"):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {
        "airpods_mac": mac.upper(),
        "mic_source": mic_source,
        "pipewire_rate": int(rate),
        "loop_latency_frames": int(latency_frames),
        "bt_profile": profile,
    }
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
    print(f"\nWrote config to: {CONFIG_PATH}")


def install_service():
    run(["loginctl", "enable-linger", os.getenv("USER", "")], check=False)

    SERVICE_DIR.mkdir(parents=True, exist_ok=True)
    python_exec = sys.executable
    boot_script = str((Path(__file__).parent / "mic2airpods_boot.py").resolve())

    service = f"""[Unit]
Description=Mic array -> AirPods (HFP) low-latency loopback
After=pipewire.service pipewire-pulse.service wireplumber.service bluetooth.service
Wants=pipewire.service pipewire-pulse.service wireplumber.service

[Service]
Type=simple
ExecStart={python_exec} {boot_script}
Restart=always
RestartSec=2

[Install]
WantedBy=default.target
"""
    SERVICE_PATH.write_text(service)
    print(f"Wrote service file to: {SERVICE_PATH}")

    run(["systemctl", "--user", "daemon-reload"], check=False)
    run(["systemctl", "--user", "enable", "--now", "mic2airpods.service"], check=False)
    print("Enabled and started mic2airpods.service (user service).")


def pair_trust_connect(mac):
    restart_bluetooth_service()

    if not wait_for_bluetoothd():
        print("Bluetooth service is not active.")
        sys.exit(1)

    print("Powering on Bluetooth adapter...")
    print(bluetoothctl(["power on"], timeout=10))

    found = scan_for_device(mac, scan_seconds=20)
    if not found:
        raise RuntimeError(
            f"Device {mac} was not found.\n"
            "Make sure the AirPods are in pairing mode and not connected to another device."
        )

    print("\nAirPods found. Pairing...")

    p = subprocess.Popen(
        ["bluetoothctl"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        p.stdin.write("power on\n")
        p.stdin.write(f"pair {mac}\n")
        p.stdin.flush()

        paired = False
        start = time.time()
        while time.time() - start < 30:
            line = p.stdout.readline()
            if not line:
                time.sleep(0.1)
                continue

            line = line.rstrip()
            print(line)

            if ("Pairing successful" in line or
                "Paired: yes" in line or
                "Connection successful" in line):
                paired = True
                break

            if ("Failed to pair" in line or
                "AuthenticationFailed" in line or
                "not available" in line):
                break

        p.stdin.write("quit\n")
        p.stdin.flush()
    finally:
        try:
            p.terminate()
        except Exception:
            pass

    if not paired:
        raise RuntimeError(
            "Pairing did not complete successfully. "
            "Keep the AirPods in pairing mode and disconnect them from your phone/laptop first."
        )

    print("\nTrusting device...")
    out = bluetoothctl([f"trust {mac}"], timeout=15)
    print(out)

    print("\nConnecting...")
    out = bluetoothctl([f"connect {mac}"], timeout=20)
    print(out)

    cards = run(["pactl", "list", "cards", "short"], check=False, capture=True)
    expected_card = f"bluez_card.{mac.replace(':', '_').upper()}"
    if expected_card in cards.stdout:
        print(f"\nBluetooth card detected: {expected_card}")
    else:
        print(f"\nWarning: {expected_card} not visible yet in pactl list cards short.")


def main():
    ensure_deps()

    print("=== First-time setup: Mic array -> AirPods over HFP ===")
    mac = input("Enter AirPods Bluetooth MAC (string id, e.g. AA:BB:CC:DD:EE:FF): ").strip()
    if not validate_mac(mac):
        print("That doesn't look like a MAC address. Format must be AA:BB:CC:DD:EE:FF")
        sys.exit(1)

    print("\nPut AirPods in pairing mode now (case open, hold button until flashing).")
    input("Press Enter to continue...")

    try:
        pair_trust_connect(mac)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print("\nNow choose your microphone array source.")
    mic_source = choose_mic_source()

    print("\nLoopback latency setting:")
    print("  64  = lowest (may crackle)")
    print("  128 = recommended start")
    print("  256 = safer (more latency)")
    lf = input("Choose frames [128]: ").strip()
    latency_frames = int(lf) if lf.isdigit() else 128

    write_config(mac, mic_source, latency_frames=latency_frames, rate=48000, profile="headset-head-unit")

    install = input("\nInstall & enable boot service now? [Y/n]: ").strip().lower()
    if install in ("", "y", "yes"):
        install_service()
        print("\nDone. Reboot to test boot autostart.")
    else:
        print("\nSetup complete. You can run mic2airpods_boot.py manually to test.")


if __name__ == "__main__":
    main()