"""
Step 1 (v2): Ping RTT Variance — Real WiFi Sensing
====================================================
RSSI Windows pe clamp hota hai, RTT nahi hota.
Ye script router ko continuously ping karti hai
aur RTT variance se presence/movement detect karti hai.

Run: python ping_sense.py
Router IP change karo agar alag hai.
"""

import subprocess
import re
import time
import json
import os
import statistics
from datetime import datetime
from collections import deque

ROUTER_IP   = "192.168.1.1"   # ← apna router IP yahan
PING_COUNT  = 1                # per reading kitne pings
INTERVAL    = 0.2              # seconds between readings
LOG_FILE    = "rtt_log.jsonl"
WINDOW      = 20               # kitne readings ka window rakhein


def find_router_ip():
    """Auto-detect router IP"""
    try:
        result = subprocess.run(
            ["ipconfig"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split("\n"):
            if "Default Gateway" in line:
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    return match.group(1)
    except:
        pass
    return None


def ping_once(ip):
    """Single ping, returns RTT in ms or None"""
    try:
        result = subprocess.run(
            ["ping", "-n", "1", "-w", "500", ip],
            capture_output=True, text=True, timeout=2
        )
        match = re.search(r"Average = (\d+)ms", result.stdout)
        if match:
            return float(match.group(1))
        match = re.search(r"time[=<](\d+)ms", result.stdout)
        if match:
            return float(match.group(1))
        if "time<1ms" in result.stdout:
            return 0.5
        return None
    except:
        return None


def classify(rtt_window):
    """
    RTT window se presence classify karo.
    Returns: (state, confidence, reason)
    """
    if len(rtt_window) < 5:
        return "calibrating", 0, "need more data"

    avg  = statistics.mean(rtt_window)
    std  = statistics.stdev(rtt_window) if len(rtt_window) > 1 else 0
    rng  = max(rtt_window) - min(rtt_window)

    if std > 2.5:
        return "MOVEMENT", min(100, int(std * 15)), f"high variance σ={std:.1f}ms"
    elif std > 1.2:
        return "Possible presence", min(100, int(std * 20)), f"elevated variance σ={std:.1f}ms"
    else:
        return "Clear / stable", max(0, 100 - int(std * 30)), f"low variance σ={std:.1f}ms"


def sparkline(values, width=30):
    """Mini ASCII chart"""
    if not values:
        return ""
    chars = " ▁▂▃▄▅▆▇█"
    mn, mx = min(values), max(values)
    rng = mx - mn if mx != mn else 1
    result = ""
    for v in list(values)[-width:]:
        idx = min(int(((v - mn) / rng) * 8), 8)
        result += chars[idx]
    return result


def bar(value, max_val=10, width=20):
    chars_filled = min(int((value / max_val) * width), width)
    return "█" * chars_filled + "░" * (width - chars_filled)


def clear():
    os.system("cls" if os.name == "nt" else "clear")


def main():
    global ROUTER_IP

    print("Ping RTT Sensor — detecting router IP...")
    auto_ip = find_router_ip()
    if auto_ip:
        ROUTER_IP = auto_ip
        print(f"Auto-detected router: {ROUTER_IP}")
    else:
        print(f"Using default: {ROUTER_IP}")
        print("(Change ROUTER_IP in script if wrong)")

    time.sleep(1)

    # Test connectivity
    test = ping_once(ROUTER_IP)
    if test is None:
        print(f"\nERROR: Cannot ping {ROUTER_IP}")
        print("Check: 1) WiFi connected  2) Router IP correct")
        print("Try: ipconfig  and look for 'Default Gateway'")
        return

    print(f"Connected! Baseline RTT: {test}ms\n")
    time.sleep(0.5)

    rtt_window  = deque(maxlen=WINDOW)
    all_readings = []
    n = 0
    baseline_rtts = deque(maxlen=50)

    with open(LOG_FILE, "a") as logf:
        while True:
            rtt = ping_once(ROUTER_IP)
            n  += 1
            ts  = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            if rtt is None:
                rtt = 999.0  # packet loss — itself a signal!

            rtt_window.append(rtt)
            all_readings.append(rtt)

            state, confidence, reason = classify(list(rtt_window))

            record = {
                "t":     ts,
                "n":     n,
                "rtt":   rtt,
                "state": state,
                "conf":  confidence,
                "std":   round(statistics.stdev(rtt_window), 2) if len(rtt_window) > 1 else 0,
            }
            logf.write(json.dumps(record) + "\n")
            logf.flush()

            clear()
            print("╔══════════════════════════════════════════════╗")
            print("║     Ping RTT Sensor — WiFi Presence v1      ║")
            print("╚══════════════════════════════════════════════╝")
            print(f"\n  Router : {ROUTER_IP}")
            print(f"  Reading: #{n}  at  {ts}")

            print(f"\n  ── Current RTT ──")
            rtt_display = f"{rtt:.1f}ms" if rtt < 900 else "TIMEOUT"
            rtt_bar_val = min(rtt, 20)
            print(f"  {bar(rtt_bar_val, 20)}  {rtt_display}")

            if len(rtt_window) > 1:
                std = statistics.stdev(rtt_window)
                avg = statistics.mean(rtt_window)
                mn  = min(rtt_window)
                mx  = max(rtt_window)
                print(f"\n  ── Window Stats (last {len(rtt_window)} pings) ──")
                print(f"  Avg : {avg:.1f}ms   Min: {mn:.1f}ms   Max: {mx:.1f}ms")
                print(f"  σ   : {std:.2f}ms  {bar(min(std, 5), 5)}  ← KEY metric")

            print(f"\n  ── Detection ──")
            icon = "🔴" if "MOVEMENT" in state else ("🟡" if "presence" in state.lower() else "🟢")
            print(f"  {icon}  {state}")
            print(f"      {reason}")
            print(f"      Confidence: {confidence}%")

            if len(rtt_window) > 3:
                spark = sparkline(list(rtt_window))
                print(f"\n  RTT history: {spark}")
                print(f"             ↑ low = stable, peaks = disturbance")

            print(f"\n  Log: {LOG_FILE} ({n} readings)")
            print("\n  EXPERIMENTS to try:")
            print("  1. Stand between laptop & router → RTT should spike")
            print("  2. Wave your hand at router → watch σ increase")
            print("  3. Leave room → should go back to stable/green")
            print("\n  Ctrl+C to stop")

            time.sleep(INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nStopped! Log saved to", LOG_FILE)
        print("Share the log and we'll analyze patterns together.")