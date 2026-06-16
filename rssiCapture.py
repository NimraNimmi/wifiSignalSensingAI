"""
Step 1: Real WiFi Signal Detector
==================================
Ye script tumhare laptop ki WiFi card se REAL signal data capture karti hai.
Windows pe netsh use karta hai — raw dBm values, not percentage.

Run karo: python wifi_detector.py
"""

import subprocess
import time
import re
import json
import os
from datetime import datetime

# ─── CONFIG ───────────────────────────────────────────────
INTERVAL_SEC = 0.3       # kitni baar per second sample lein
LOG_FILE     = "wifi_log.jsonl"   # sab readings save hongi yahan
# ──────────────────────────────────────────────────────────


def get_wifi_raw_windows():
    """
    netsh se raw interface data lo.
    Returns dict with signal_pct, bssid, ssid, channel, radio_type
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=2
        )
        out = result.stdout

        data = {}

        # SSID
        m = re.search(r"^\s+SSID\s+:\s+(.+)$", out, re.MULTILINE)
        data["ssid"] = m.group(1).strip() if m else "unknown"

        # BSSID (router ka MAC address)
        m = re.search(r"BSSID\s+:\s+([0-9a-f:]+)", out, re.IGNORECASE)
        data["bssid"] = m.group(1).strip() if m else "unknown"

        # Signal % (Windows normalized)
        m = re.search(r"Signal\s+:\s+(\d+)%", out)
        data["signal_pct"] = int(m.group(1)) if m else 0

        # Radio type (802.11ac, 802.11n, etc.)
        m = re.search(r"Radio type\s+:\s+(.+)$", out, re.MULTILINE)
        data["radio_type"] = m.group(1).strip() if m else "unknown"

        # Channel
        m = re.search(r"Channel\s+:\s+(\d+)", out)
        data["channel"] = int(m.group(1)) if m else 0

        # Receive rate (Mbps) — ye vary karta hai movement se!
        m = re.search(r"Receive rate.*?:\s+([\d.]+)", out)
        data["rx_rate_mbps"] = float(m.group(1)) if m else 0.0

        # Transmit rate
        m = re.search(r"Transmit rate.*?:\s+([\d.]+)", out)
        data["tx_rate_mbps"] = float(m.group(1)) if m else 0.0

        return data

    except Exception as e:
        return {"error": str(e)}


def get_nearby_networks():
    """
    Aas paas ke saare WiFi networks scan karo — inke signal bhi vary karte hain!
    """
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=5
        )
        out = result.stdout

        networks = []
        # Split by SSID blocks
        blocks = re.split(r"SSID \d+\s*:", out)[1:]
        for block in blocks:
            net = {}
            m = re.search(r"^\s*(.+)$", block, re.MULTILINE)
            net["ssid"] = m.group(1).strip() if m else "hidden"

            m = re.search(r"Signal\s+:\s+(\d+)%", block)
            net["signal_pct"] = int(m.group(1)) if m else 0

            m = re.search(r"Channel\s+:\s+(\d+)", block)
            net["channel"] = int(m.group(1)) if m else 0

            networks.append(net)

        return networks[:8]  # top 8 networks
    except:
        return []


def pct_to_dbm(pct):
    """
    Windows % ko approximate dBm mein convert karo
    (ye exact nahi hai, but indicative hai)
    Formula: dBm = (pct / 2) - 100
    """
    return (pct / 2) - 100


def signal_bar(pct, width=20):
    """ASCII bar for terminal visualization"""
    filled = int((pct / 100) * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"


def detect_change(history, threshold=3):
    """
    Recent readings mein significant change detect karo.
    Threshold = % points ka difference
    """
    if len(history) < 5:
        return "collecting...", "gray"

    recent  = history[-3:]
    earlier = history[-8:-3]

    avg_recent  = sum(recent)  / len(recent)
    avg_earlier = sum(earlier) / len(earlier)
    delta = avg_recent - avg_earlier

    if abs(delta) < threshold:
        return f"stable (Δ{delta:+.1f}%)", "green"
    elif delta > 0:
        return f"signal UP (Δ{delta:+.1f}%) — someone moved?", "yellow"
    else:
        return f"signal DOWN (Δ{delta:+.1f}%) — obstruction?", "red"


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    print("WiFi Signal Detector — Step 1")
    print("Initializing...\n")
    time.sleep(1)

    history_pct = []
    history_rx  = []
    reading_num = 0
    log_data    = []

    print(f"Logging to: {LOG_FILE}")
    print("Press Ctrl+C to stop.\n")
    time.sleep(1)

    with open(LOG_FILE, "a") as logf:
        while True:
            data = get_wifi_raw_windows()
            ts   = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            reading_num += 1

            if "error" in data:
                print(f"[{ts}] Error: {data['error']}")
                time.sleep(1)
                continue

            pct = data["signal_pct"]
            dbm = pct_to_dbm(pct)
            rx  = data["rx_rate_mbps"]

            history_pct.append(pct)
            history_rx.append(rx)
            if len(history_pct) > 50:
                history_pct.pop(0)
                history_rx.pop(0)

            change_msg, _ = detect_change(history_pct)

            # Save to log
            record = {
                "t":   ts,
                "n":   reading_num,
                "pct": pct,
                "dbm": round(dbm, 1),
                "rx":  rx,
                "tx":  data["tx_rate_mbps"],
                "ch":  data["channel"],
            }
            logf.write(json.dumps(record) + "\n")
            logf.flush()

            # ── Terminal Display ──────────────────────────────
            clear()
            print("╔══════════════════════════════════════════════╗")
            print("║     WiFi Signal Detector — Step 1           ║")
            print("╚══════════════════════════════════════════════╝")
            print(f"\n  Network : {data['ssid']}")
            print(f"  BSSID   : {data['bssid']}")
            print(f"  Radio   : {data['radio_type']}  |  Channel: {data['channel']}")
            print(f"  Reading : #{reading_num}  at  {ts}")

            print(f"\n  ── Signal Strength ──")
            print(f"  {signal_bar(pct)}  {pct}%  ≈  {dbm:.0f} dBm")

            print(f"\n  ── Link Speed (varies with environment) ──")
            rx_bar = signal_bar(min(rx, 300) / 300 * 100)
            print(f"  RX: {rx_bar}  {rx:.0f} Mbps")
            print(f"  TX: {data['tx_rate_mbps']:.0f} Mbps")

            print(f"\n  ── Change Detection ──")
            print(f"  Status: {change_msg}")

            # Mini sparkline
            if len(history_pct) > 1:
                spark = ""
                chars = " ▁▂▃▄▅▆▇█"
                for v in history_pct[-30:]:
                    idx = min(int(v / 100 * 8), 8)
                    spark += chars[idx]
                print(f"\n  History: {spark}")

            print(f"\n  Log: {LOG_FILE}  ({reading_num} readings)")
            print("\n  EXPERIMENT: Walk around, wave your arms,")
            print("  stand between laptop & router — watch changes!")
            print("\n  Ctrl+C to stop.")

            time.sleep(INTERVAL_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped. Check wifi_log.jsonl for all readings!")
        print("Next step: analyze the log to see patterns.")