import socket
import os
import time
import subprocess
import re
import hid  # python-hid package

# USB VID/PID of the Anker PowerConf S330
VID = 0x291a
PID = 0x3308

# WakeWord target: Wyoming Satellite expects WakeWord events on port 10400
WYOMING_WAKE_HOST = "127.0.0.1"
WYOMING_WAKE_PORT = 10400

def get_wakeword_name():
    """Reads the configured WakeWord name from the process arguments"""
    try:
        out = subprocess.check_output(
            "ps -ef | grep wyoming-satellite | grep -- '--wake-word-name' | head -1",
            shell=True,
            text=True
        )
        match = re.search(r"--wake-word-name\s+(\S+)", out)
        if match:
            return match.group(1)
    except Exception as e:
        print("Error determining Wake Word:", e)
    return "jarvis"  # Fallback

def send_fake_wakeword():
    """Sends a WakeWordResult event to the Wyoming Satellite (UDP)"""
    name = get_wakeword_name()
    header = b"WYOMING"
    event_name = f"wake  {name}\n".encode("utf-8")
    length = len(event_name).to_bytes(4, byteorder="big")
    reserved = b"\x00" * 4
    packet = header + length + reserved + event_name

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(packet, (WYOMING_WAKE_HOST, WYOMING_WAKE_PORT))
    print(f"📣 Fake WakeWord \"{name}\" sent to {WYOMING_WAKE_HOST}:{WYOMING_WAKE_PORT}")

def main():
    print("Starting button monitoring for Anker PowerConf S330...")

    try:
        dev = hid.device()
        dev.open(VID, PID)
        dev.set_nonblocking(True)
    except Exception as e:
        print("Error opening HID device:", e)
        return

    while True:
        try:
            data = dev.read(64)
            if data:
                report_id = data[0]
                payload = data[1] if len(data) > 1 else 0

                if report_id == 1:
                    if payload == 0x08:
                        print("🔊 VOLUME UP pressed")
                        os.system("amixer sset Master 5%+")
                    elif payload == 0x10:
                        print("🔉 VOLUME DOWN pressed")
                        os.system("amixer sset Master 5%-")
                elif report_id == 2:
                    if payload == 0x03:
                        print("📞 PHONE button pressed → triggering WakeWord")
                        send_fake_wakeword()

            time.sleep(0.05)
        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print("Error during execution:", e)
            time.sleep(1)

if __name__ == "__main__":
    main()
