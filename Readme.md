# HomeAssistant Voice Mini

![HomeAssistant Voice Mini Device](IMG_4440.jpg)

A smart home solution for voice control using Wyoming protocol with Raspberry Pi and Anker PowerConf S330.

## Hardware

- [Raspberry Pi Zero 2 W](https://www.amazon.de/Raspberry-Pi-Zero-2-W/dp/B09KLVX4RT)
- [Anker PowerConf S330](https://www.amazon.de/Anker-Lautsprecher-Konferenzlautsprecher-Raumabdeckung-A3308011/dp/B09FJ7LWX4)
- [USB-C Netzteil für Raspberry Pi](https://www.amazon.de/offizieller-Raspberry-Pi-Netzteil-Supply-Wei%C3%9F/dp/B0CM46P7MC)
- [WS2812B LED Strip 5V](https://www.amazon.de/WS2812B-Individuell-Adressierbar-Vollfarbiger-Wasserdicht/dp/B08YWQLXRS)
- [Micro USB auf USB-C Adapter](https://www.amazon.de/dp/B0DYDQRTZT)
- [USB-C Buchse](https://www.amazon.de/dp/B0CZLD8NKS)

### Wiring Diagram

| <img src="wire.png" width="350" height="350"> | <img src="IMG_4441.jpg" width="350" height="350"> |
|:-------------------------:|:-------------------------:|
| **Wiring Diagram** | **Real Implementation** |

The wiring diagram shows the connections between components:
- The WS2812B LED strip connects to the Raspberry Pi Zero 2's GPIO18 pin for data, and to power/ground
- The USB-C connector is wired to provide power to the system
- The Anker S330 connects via USB to the Raspberry Pi (not shown in diagram)

## Raspberry Pi Image
Recommended image:
Raspberry Pi Imager -> Raspberry Pi Zero 2 -> Other -> Raspbian Lite 64-bit

# Installation

## Clone Repository

```sh
# Clone the homeassistant_voice_mini repository
sudo apt-get install git -y
git clone https://github.com/tobiaskuntzsch/homeassistant_voice_mini.git
cd homeassistant_voice_mini
```

## Install Dependencies

```sh
# System dependencies
sudo apt-get update -y
sudo apt-get install --no-install-recommends git python3-dev libopenblas-dev build-essential -y

# Python packages available through apt
sudo apt-get install --no-install-recommends python3-hidapi python3-rpi.gpio python3-pip -y

# Python packages for LED control and Wyoming protocol
sudo pip3 install rpi_ws281x adafruit-circuitpython-neopixel adafruit-blinka wyoming wyoming-satellite hidapi webrtc-noise-gain pysilero-vad --break-system-packages
```

## Scripts in this Repository

### 1. s330_buttons.py

This script interfaces with the Anker PowerConf S330 device via HID protocol to monitor button presses:
- Volume Up/Down buttons control system volume
- Phone button triggers a wake word event for the voice assistant

```sh
# Run the button monitoring script with default settings
sudo python3 s330_buttons.py

# Run with debug logging
sudo python3 s330_buttons.py --debug

# Specify a custom wake word
sudo python3 s330_buttons.py --wake-word "alexa"

# Specify audio control for volume buttons
sudo python3 s330_buttons.py --audio-control "PCM"

# For the Anker PowerConf S330 USB audio device (preferred)
sudo python3 s330_buttons.py --audio-control "Anker PowerConf S330"

# Write logs to a file
sudo python3 s330_buttons.py --log-file="/var/log/s330_buttons.log"
```

Available parameters:
- `--debug`: Enable detailed debug logging
- `--log-file`: Path to write log output
- `--audio-control`: Audio mixer control to use (e.g., Master, PCM, Speaker)
- `--wake-word`: Wake word to use when triggering (overrides auto-detection)
- `--wyoming-host`: Wyoming host (default: 127.0.0.1)
- `--wyoming-port`: Wyoming UDP port (default: 10400)

### 2. neopixel_led_service.py

This script controls a WS2812B LED strip to provide visual feedback for Wyoming events:
- Blue when wake word is detected
- Yellow during streaming/voice activity
- Green when transcript is received
- Red when satellite is disconnected

The script is configurable with several command line parameters:

```sh
# Run the LED service with default settings (1 LED on pin 18)
sudo python3 neopixel_led_service.py --uri 'tcp://127.0.0.1:10500'

# Configure the LED strip parameters
sudo python3 neopixel_led_service.py --uri 'tcp://127.0.0.1:10500' \
  --num-leds 8 \
  --pin 18 \
  --led-brightness 0.3
```

Available parameters:
- `--uri`: Wyoming event URI (required)
- `--num-leds`: Number of LEDs in the strip (default: 1)
- `--pin`: GPIO pin number for the LED strip (default: 18, which is D18)
- `--led-brightness`: LED brightness from 0.0 to 1.0 (default: 0.5)
- `--debug`: Enable debug logging

## Find Anker S330 Device

```sh
aplay -L | grep -i s330 | grep -i plughw
# Expected output: plughw:CARD=S330,DEV=0
```

# Setting Up as Services

## Service Installation Sequence

The services should be set up and started in the following order:

1. **homeassistant-voice-mini-leds.service** - LED feedback service
2. **wyoming-openwakeword.service** - Wake word detection (optional)
3. **wyoming-satellite.service** - Wyoming protocol integration
4. **homeassistant-voice-mini-buttons.service** - Anker S330 button service

## 1. LED Service (homeassistant-voice-mini-leds.service)

### Create Service File

```sh
sudo systemctl edit --force --full homeassistant-voice-mini-leds.service
```

Add the following content:

```ini
[Unit]
Description=NeoPixel LEDs Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/homeassistant_voice_mini/neopixel_led_service.py --uri 'tcp://127.0.0.1:10500'
WorkingDirectory=/home/pi/homeassistant_voice_mini
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Enable and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable homeassistant-voice-mini-leds.service
sudo systemctl start homeassistant-voice-mini-leds.service
sudo systemctl status homeassistant-voice-mini-leds.service
```

## 2. Wake Word Service (Optional)

> **Note:** Alternatively, you can use a central OpenWakeWord service in your network instead of installing it locally. In this case, you only need to adjust the IP address of the central service in the Wyoming Satellite configuration under `--wake-uri` (e.g., `--wake-uri 'tcp://192.168.1.100:10400'`).

### Setting up Wyoming OpenWakeWord

```sh
# Clone the OpenWake repository
git clone https://github.com/rhasspy/wyoming-openwakeword.git
cd ~/wyoming-openwakeword

# Setup OpenWake
script/setup

# Download models (optional)
script/download-models

# Test available models
.venv/bin/wyoming-openwakeword --list-models
```

### Create Service File

```sh
sudo systemctl edit --force --full wyoming-openwake.service
```

Add the following content:

```ini
[Unit]
Description=Wyoming OpenWakeWord Service
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=/home/pi/wyoming-openwakeword/script/run \
  --uri 'tcp://0.0.0.0:10400' \
  --preload-model 'ok_homeassistant_voice_mini' \
  --threshold 0.8
WorkingDirectory=/home/pi/wyoming-openwakeword
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Enable and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable wyoming-openwake.service
sudo systemctl start wyoming-openwake.service
sudo systemctl status wyoming-openwake.service
```

## 3. Wyoming Satellite Service

### Setting up Wyoming Satellite

> **IMPORTANT:** We need to use a custom version of Wyoming Satellite with enhanced functionality. This version includes a Web API for controlling the satellite and supports direct activation without speaking a wake word.

```sh
# Clone our custom Wyoming Satellite repository
cd $HOME
git clone https://github.com/tobiaskuntzsch/wyoming-satellite.git
cd ~/wyoming-satellite

# Ensure you have the latest version
git pull

# Setup Wyoming Satellite
script/setup
script/setup --api

# Install additional audio processing packages
.venv/bin/pip3 install 'pysilero-vad==1.0.0'
.venv/bin/pip3 install 'webrtc-noise-gain==1.2.3'

# Check available options
script/run --help
```

### Create Service File

```sh
sudo systemctl edit --force --full wyoming-satellite.service
```

Add the following content:

```ini
[Unit]
Description=Wyoming Satellite
Wants=network-online.target
After=network-online.target
Requires=homeassistant-voice-mini-leds.service

[Service]
Type=simple
ExecStart=/home/pi/wyoming-satellite/script/run \
  --name 'HomeAssistant Voice Mini <ROOM NAME>' \
  --uri 'tcp://0.0.0.0:10700' \
  --mic-command 'arecord -D plughw:CARD=S330,DEV=0 -r 16000 -c 1 -f S16_LE -t raw' \
  --snd-command 'aplay -D plughw:CARD=S330,DEV=0 -r 16000 -c 1 -f S16_LE -t raw' \
  --mic-auto-gain 7 \
  --mic-noise-suppression 3 \
  --wake-uri 'tcp://127.0.0.1:10400' \
  --wake-word-name 'ok_nabu' \
  --event-uri 'tcp://127.0.0.1:10500' \
  --snd-command-rate 16000 \
  --snd-volume-multiplier 0.2 \
  --awake-wav sounds/awake.wav \
  --done-wav sounds/done.wav \
  --api-uri 'http://127.0.0.1:8080'
WorkingDirectory=/home/pi/wyoming-satellite
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Enable and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable wyoming-satellite.service
sudo systemctl start wyoming-satellite.service
sudo systemctl status wyoming-satellite.service
```


## 4. Button Service (homeassistant-voice-mini-buttons.service)

### Create Service File

```sh
sudo systemctl edit --force --full homeassistant-voice-mini-buttons.service
```

Add the following content:

```ini
[Unit]
Description=Anker S330 Button Service
After=network-online.target wyoming-satellite.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /home/pi/homeassistant_voice_mini/s330_buttons.py --audio-control "Anker PowerConf S330"
WorkingDirectory=/home/pi/homeassistant_voice_mini
Restart=always
RestartSec=1

[Install]
WantedBy=default.target
```

Enable and start the service:

```sh
sudo systemctl daemon-reload
sudo systemctl enable homeassistant-voice-mini-buttons.service
sudo systemctl start homeassistant-voice-mini-buttons.service
sudo systemctl status homeassistant-voice-mini-buttons.service
```

## Verification & Troubleshooting

### Check Service Status

```sh
# Check all services status
sudo systemctl status homeassistant-voice-mini-leds.service wyoming-satellite.service homeassistant-voice-mini-buttons.service

# Or check individual services
sudo systemctl status homeassistant-voice-mini-buttons.service
```

### View Service Logs

```sh
# View the logs for the button service
journalctl -u homeassistant-voice-mini-buttons.service -f

# View the logs for the LED service
journalctl -u homeassistant-voice-mini-leds.service -f

# View the logs for Wyoming Satellite
journalctl -u wyoming-satellite.service -f
```

### Restart Services

If you need to restart services after making changes:

```sh
sudo systemctl daemon-reload
sudo systemctl restart homeassistant-voice-mini-leds.service
sudo systemctl restart wyoming-openwake.service
sudo systemctl restart wyoming-satellite.service
sudo systemctl restart homeassistant-voice-mini-buttons.service
```

With this setup, the wake word detection happens locally on your HomeAssistant Voice Mini device.

To use a remote wake word service instead, modify the `--wake-uri` in the Wyoming Satellite service to point to your remote server.

# 3D Printed Case

The HomeAssistant Voice Mini comes with 3D printable case files to create a nice enclosure for your device.

## 3D Models

- [HomeAssistant Voice Mini - Body (V5)](HomeAssistantVoiceMini%20-%20Body%20-%20V5.stl) - The main enclosure
- [HomeAssistant Voice Mini - Window (V1)](HomeAssistantVoiceMini%20-%20Window%20-%20V1.stl) - Transparent window part

## Printing Recommendations

- Print the main body with regular PLA (recommended 0.2mm layer height)
- Print the window with transparent material for better LED visibility

![3D Printed Case Preview](3dprint.png)

View these STL files in your favorite slicer software (like Cura, PrusaSlicer, etc.) to prepare for printing.
