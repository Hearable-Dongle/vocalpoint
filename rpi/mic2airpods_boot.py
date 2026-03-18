#!/usr/bin/env python3
import json
import shutil
import subprocess
import time
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "mic2airpods" / "config.json"


def have(cmd):
    return shutil.which(cmd) is not None


def run(cmd, check=True, capture=False, input_data=None):
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
        input=input_data,
    )


def ensure_deps():
    missing = [c for c in ["pactl", "pw-loopback", "bluetoothctl", "pkill"] if not have(c)]
    if missing:
        print("Missing required commands:", ", ".join(missing))
        return False
    return True


def wait_for_pactl(max_s=20):
    t0 = time.time()
    while time.time() - t0 < max_s:
        r = subprocess.run(
            ["pactl", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if r.returncode == 0:
            return True
        time.sleep(0.25)
    return False


def bluetoothctl_batch(commands, timeout=20):
    input_data = "\n".join(commands) + "\nquit\n"
    result = subprocess.run(
        ["bluetoothctl"],
        input=input_data,
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    return result


def bluetooth_connect(mac):
    result = bluetoothctl_batch(
        [
            "power on",
            f"connect {mac}",
        ],
        timeout=25,
    )
    return result.returncode == 0


def card_name_from_mac(mac):
    return "bluez_card." + mac.replace(":", "_").upper()


def find_airpods_sink(mac_underscored):
    r = run(["pactl", "list", "sinks", "short"], check=False, capture=True)
    for line in r.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            name = parts[1]
            if name.startswith(f"bluez_output.{mac_underscored}"):
                return name
    return None


def source_exists(source_name):
    r = run(["pactl", "list", "sources", "short"], check=False, capture=True)
    return source_name in r.stdout


def card_exists(card_name):
    r = run(["pactl", "list", "cards", "short"], check=False, capture=True)
    return card_name in r.stdout


def set_bt_profile(card, profile):
    result = subprocess.run(
        ["pactl", "set-card-profile", card, profile],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def start_loopback(mic_source, sink_name, frames, rate):
    subprocess.run(
        ["pkill", "-f", "pw-loopback.*mic2airpods"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    cmd = [
        "pw-loopback",
        "--name",
        "mic2airpods",
        "--capture",
        mic_source,
        "--playback",
        sink_name,
        "--latency",
        f"{frames}/{rate}",
    ]
    return subprocess.Popen(cmd)


def main():
    if not ensure_deps():
        return 1

    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}")
        print("Run setup_first_time.py first.")
        return 2

    cfg = json.loads(CONFIG_PATH.read_text())
    mac = cfg["airpods_mac"]
    mic_source = cfg["mic_source"]
    rate = int(cfg.get("pipewire_rate", 48000))
    frames = int(cfg.get("loop_latency_frames", 128))
    profile = cfg.get("bt_profile", "headset-head-unit")

    mac_underscored = mac.replace(":", "_").upper()
    card = card_name_from_mac(mac)

    if not wait_for_pactl(20):
        print("pactl not available (pipewire-pulse not ready).")
        return 1

    proc = None
    last_connect_attempt = 0.0
    connect_retry_interval = 5.0

    while True:
        if not source_exists(mic_source):
            print(f"Mic source not found: {mic_source}")
            if proc is not None and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=2)
                proc = None
            time.sleep(2)
            continue

        sink = find_airpods_sink(mac_underscored)
        card_present = card_exists(card)

        if not card_present or not sink:
            now = time.time()
            if now - last_connect_attempt >= connect_retry_interval:
                print(f"Connecting to AirPods {mac}...")
                bluetooth_connect(mac)
                last_connect_attempt = now

            for _ in range(40):
                card_present = card_exists(card)
                if card_present:
                    break
                time.sleep(0.25)

            if card_present:
                if not set_bt_profile(card, profile):
                    print(f"Warning: failed to set Bluetooth profile {profile} on {card}")
                time.sleep(1.0)
                sink = find_airpods_sink(mac_underscored)

        if sink:
            if proc is None or proc.poll() is not None:
                print(f"Starting loopback: {mic_source} -> {sink}")
                proc = start_loopback(mic_source, sink, frames, rate)
        else:
            if proc is not None and proc.poll() is None:
                print("Bluetooth sink disappeared; stopping loopback.")
                proc.terminate()
                proc.wait(timeout=2)
                proc = None

        time.sleep(1.0)

        if proc is not None and proc.poll() is not None:
            print("pw-loopback exited; restarting...")
            proc = None


if __name__ == "__main__":
    raise SystemExit(main())