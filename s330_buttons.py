import os
import time
import subprocess
import re
import json
import logging
import datetime
import argparse
import requests

# Konfiguriere das Logging
logger = logging.getLogger("s330_buttons")

# Format: [ZEIT] [LEVEL] [NACHRICHT]
log_format = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', 
                             datefmt='%Y-%m-%d %H:%M:%S')

# USB VID/PID of the Anker PowerConf S330
VID = 0x291a
PID = 0x3308

# Wyoming Satellite Web API details
WYOMING_API_HOST = "127.0.0.1"
WYOMING_API_PORT = 8080
WYOMING_API_BASE_URL = f"http://{WYOMING_API_HOST}:{WYOMING_API_PORT}/api"

def get_available_audio_controls():
    """Determines available audio controls for volume adjustment"""
    mixer_controls = []
    
    try:
        # Versuche zuerst, alle verfügbaren Mixer zu bekommen
        out = subprocess.check_output(["amixer", "scontrols"], text=True)
        logger.debug(f"amixer scontrols output:\n{out}")
        
        # Suche nach Mustern wie 'Simple mixer control 'Master',0' oder 'Simple mixer control 'PCM',0'
        controls = re.findall(r"Simple mixer control '([^']+)',\d+", out)
        
        if controls:
            logger.debug(f"Found audio controls: {controls}")
            mixer_controls = controls
        else:
            logger.warning("No audio controls found in output format we expected")
    except Exception as e:
        logger.error(f"Error finding audio controls: {e}")
    
    # Priorisiere gängige Namen, wenn sie gefunden wurden
    if mixer_controls:
        for preferred in ['Master', 'PCM', 'Speaker', 'Headphone', 'Digital']:
            if preferred in mixer_controls:
                logger.info(f"Using '{preferred}' audio control for volume adjustment")
                return preferred
        
        # Wenn keine der bevorzugten gefunden wurde, nehmen wir den ersten
        first_control = mixer_controls[0]
        logger.info(f"Using '{first_control}' audio control for volume adjustment")
        return first_control
    
    # Fallback auf Master, wenn nichts gefunden wurde
    logger.warning("No audio controls found, audio buttons will be disabled")
    return None  # Rückgabe von None signalisiert, dass keine Lautstärkeanpassung möglich ist

def get_wakeword_name():
    """Reads the configured WakeWord name from the process arguments"""
    try:
        # Erweiterte Suche nach dem Wyoming-Satellite-Prozess
        commands = [
            "ps -ef | grep wyoming-satellite | grep -v grep | grep -- '--wake-word-name' | head -1",
            "ps -ef | grep wyoming-satellite | grep -v grep | head -1",
            "ps aux | grep wyoming-satellite | grep -v grep | head -1"
        ]
        
        for cmd in commands:
            try:
                out = subprocess.check_output(cmd, shell=True, text=True)
                if out.strip():
                    # Versuche, den Wake-Word-Namen zu extrahieren
                    match = re.search(r"--wake-word-name[= ]([\w-]+)", out)
                    if match:
                        wake_word = match.group(1)
                        logger.info(f"Found wake word: {wake_word}")
                        return wake_word
                    else:
                        logger.warning(f"Wyoming-satellite process found but no wake-word-name argument detected")
            except subprocess.CalledProcessError:
                continue
        
        logger.warning("Could not find Wyoming Satellite process, using default wake word")
    except Exception as e:
        logger.error(f"Error determining Wake Word: {e}")
        
    default_wake_word = "jarvis"    
    logger.warning(f"Using default wake word: {default_wake_word}")
    return default_wake_word  # Fallback

def toggle_satellite_state():
    """Schaltet den Wyoming Satellite zwischen den Zuständen um.
    
    Wenn der Satellite gerade aktiv ist (hört oder streamt Audio), wird er abgebrochen.
    Wenn er inaktiv ist, wird ein Wakeword ausgelöst.    
    """
    try:
        # Prüfe den aktuellen Status des Satellites über die Web-API
        response = requests.get(f"{WYOMING_API_BASE_URL}/status", timeout=2)
        if response.status_code != 200:
            logger.error(f"Failed to get satellite status: HTTP {response.status_code}")
            return
            
        status = response.json()
        logger.debug(f"Current satellite status: {status}")
        
        # Entscheide basierend auf dem Status, was zu tun ist
        if status.get("is_active", False) or status.get("state", "idle") != "idle":
            # Satellite ist aktiv, sende cancel
            logger.info("Satellite is active, sending cancel request")
            cancel_response = requests.post(f"{WYOMING_API_BASE_URL}/cancel", timeout=2)
            if cancel_response.status_code == 200:
                logger.info("Cancel request successful")
            else:
                logger.error(f"Cancel request failed: HTTP {cancel_response.status_code}")
        else:
            # Satellite ist inaktiv, sende trigger-wakeword
            logger.info("Satellite is idle, triggering wake word")
            trigger_response = requests.post(f"{WYOMING_API_BASE_URL}/trigger-wakeword", timeout=2)
            if trigger_response.status_code == 200:
                logger.info("Trigger wake word request successful")
            else:
                logger.error(f"Trigger wake word request failed: HTTP {trigger_response.status_code}")
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error communicating with Wyoming Satellite API: {e}")
    except Exception as e:
        logger.error(f"Unexpected error in toggle_satellite_state: {e}")


def force_activate_satellite():
    """Aktiviert den Wyoming Satellite direkt, ohne Wake-Word-Erkennung (Force Activate).
    
    Diese Funktion verwendet die Web-API, um den Satellite direkt zu aktivieren.
    (Alias für direkten API-Aufruf, für Kompatibilität mit bestehendem Code)
    """
    try:
        # Direkte Aktivierung des Satellites über die Web-API
        logger.info("Aktiviere Wyoming Satellite direkt über Web-API")
        response = requests.post(f"{WYOMING_API_BASE_URL}/force-activate", timeout=2)
        
        if response.status_code == 200:
            logger.info("Force Activate über Web-API erfolgreich gesendet")
        else:
            logger.error(f"Force Activate fehlgeschlagen: HTTP {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Fehler bei der Kommunikation mit Wyoming Satellite API: {e}")
    except Exception as e:
        logger.error(f"Unerwarteter Fehler bei Force Activate: {e}")

def send_wyoming_message(sock, protocol_header, message):
    """Hilfsfunktion zum Senden von Wyoming-Nachrichten"""
    # Konvertiere das Message-Objekt in JSON
    data_json = json.dumps(message)
    data_bytes = data_json.encode("utf-8")
    
    # Länge und reservierte Bytes im WYOMING-Protokoll
    length = len(data_bytes).to_bytes(4, byteorder="big")
    reserved = b"\x00" * 4
    
    # Paket zusammensetzen
    packet = protocol_header + length + reserved + data_bytes
    
    # Daten senden
    sock.sendall(packet)


def setup_logging(log_level=logging.INFO, log_file=None):
    """Konfiguriert das Logging-System"""
    # Root-Logger konfigurieren
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Console-Handler
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(log_format)
    root_logger.addHandler(console)
    
    # Datei-Handler, falls eine Log-Datei angegeben wurde
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(log_format)
        root_logger.addHandler(file_handler)
    
    return root_logger

def main():
    # Kommandozeilenargumente parsen
    parser = argparse.ArgumentParser(description='Anker PowerConf S330 Button Monitor')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    parser.add_argument('--log-file', help='Path to log file')
    parser.add_argument('--audio-control', help='Audio mixer control to use (e.g., Master, PCM, Speaker)')
    parser.add_argument('--wake-word', help='Wake word to use when triggering (overrides auto-detection)')
    parser.add_argument('--wyoming-host', default=WYOMING_WAKE_HOST, help='Wyoming host (default: 127.0.0.1)')
    parser.add_argument('--wyoming-port', type=int, default=WYOMING_WAKE_PORT, help='Wyoming UDP port (default: 10400)')
    args = parser.parse_args()
    
    # Logging einrichten
    log_level = logging.DEBUG if args.debug else logging.INFO
    setup_logging(log_level, args.log_file)
    
    logger.info("Starting button monitoring for Anker PowerConf S330...")
    
    # Versuche zuerst, das hidapi-Modul zu importieren
    try:
        import hidapi
        logger.info("Using hidapi module")
        using_hid = False
    except ImportError:
        # Wenn hidapi nicht verfügbar ist, verwende hid
        try:
            import hid
            logger.info("Using hid module")
            using_hid = True
        except ImportError:
            logger.error("Neither 'hidapi' nor 'hid' module found. Please install one of them.")
            logger.error("  sudo pip3 install hidapi --break-system-packages")
            return

    # Anker S330 finden und öffnen
    device = None
    
    try:
        if using_hid:
            # Alte Methode mit hid-Paket
            device = hid.device()
            device.open(VID, PID)
            device.set_nonblocking(True)
            logger.info("Device opened with hid module")
        else:
            # Neue Methode mit hidapi-Paket
            found = False
            logger.info(f"Searching for Anker S330 device (VID: {hex(VID)}, PID: {hex(PID)})")
            for info in hidapi.enumerate():
                try:
                    # Versuche, die Vendor- und Produkt-ID zu bekommen
                    v_id = getattr(info, 'vendor_id', None)
                    p_id = getattr(info, 'product_id', None)
                    
                    if v_id is None and hasattr(info, 'get') and callable(info.get):
                        # Versuch, die IDs via dictionary-like interface zu bekommen
                        v_id = info.get('vendor_id')
                        p_id = info.get('product_id')
                    
                    # Wenn wir im Debug-Modus sind, zeige alle gefundenen Geräte an
                    if args.debug:
                        logger.debug(f"Found HID device: {v_id=:04x}, {p_id=:04x}")
                    
                    if v_id == VID and p_id == PID:
                        found = True
                        path = getattr(info, 'path', None)
                        logger.info(f"Found Anker S330 device")
                        break
                except Exception as e:
                    logger.error(f"Error accessing device info: {e}")
                    continue
                    
            if not found:
                logger.error(f"Anker S330 device not found (VID: {hex(VID)}, PID: {hex(PID)})")
                return
                
            # Versuche, das Gerät zu öffnen
            try:
                device = hidapi.Device(vendor_id=VID, product_id=PID)
                logger.info("Device opened via vendor/product ID")
            except Exception as e:
                logger.warning(f"Error opening by ID: {e}")
                if path:
                    try:
                        device = hidapi.Device(path=path)
                        logger.info("Device opened via path")
                    except Exception as e:
                        raise Exception(f"Failed to open device via path: {e}")
                else:
                    raise Exception("No path available for device")
    except Exception as e:
        logger.error(f"Error setting up HID device: {e}")
        return

    # Bestimme den zu verwendenden Audio-Mixer-Control
    audio_control = args.audio_control if args.audio_control else get_available_audio_controls()
    
    # Wyoming-Konfiguration
    wyoming_host = args.wyoming_host
    wyoming_port = args.wyoming_port
    wake_word = args.wake_word
    
    if wake_word:
        logger.info(f"Using manually specified wake word: {wake_word}")
    
    logger.info(f"Wyoming configuration: {wyoming_host}:{wyoming_port}")
    
    # Hauptschleife zum Lesen der Tasten
    try:
        logger.info("Monitoring for button presses...")
        button_count = {}
        while True:
            try:
                # Lese Daten vom Gerät
                if using_hid:
                    # Mit hid-Paket
                    data = device.read(64)
                else:
                    # Mit hidapi-Paket
                    try:
                        data = device.read(64, timeout_ms=100)
                    except Exception as e:
                        logger.debug(f"Error reading data: {e}")
                        time.sleep(0.1)
                        continue

                # Wenn Daten empfangen wurden, verarbeite sie
                if data and len(data) > 1:
                    # Debug-Ausgabe für Datenpakete, falls gewünscht
                    if args.debug:
                        logger.debug(f"Received data: {data}")
                    
                    report_id = data[0]
                    payload = data[1]
                    
                    # Erstelle einen eindeutigen Schlüssel für diesen Button
                    button_key = f"{report_id}:{payload}"
                    # Initialisiere oder erhöhe den Zähler für diesen Button
                    button_count[button_key] = button_count.get(button_key, 0) + 1
                    count = button_count[button_key]

                    if report_id == 1:
                        if payload == 0x08:
                            logger.info(f"🔊 BUTTON: VOLUME UP pressed (count: {count})")
                            if audio_control:
                                try:
                                    # Verwende den erkannten Audio-Control
                                    cmd = f"amixer sset '{audio_control}' 5%+"
                                    logger.debug(f"Running command: {cmd}")
                                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                                    if result.returncode != 0:
                                        logger.warning(f"Volume up command failed: {result.stderr.strip()}")
                                    else:
                                        logger.debug(f"Volume up command succeeded: {result.stdout.strip()}")
                                except Exception as e:
                                    logger.error(f"Error adjusting volume up: {e}")
                            else:
                                logger.warning("Volume UP pressed but no audio control available")
                                # Alternativ könnten wir hier XF86AudioRaiseVolume-Taste simulieren
                                # oder einen anderen Weg nutzen, die Lautstärke anzupassen
                        elif payload == 0x10:
                            logger.info(f"🔉 BUTTON: VOLUME DOWN pressed (count: {count})")
                            if audio_control:
                                try:
                                    # Verwende den erkannten Audio-Control
                                    cmd = f"amixer sset '{audio_control}' 5%-"
                                    logger.debug(f"Running command: {cmd}")
                                    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                                    if result.returncode != 0:
                                        logger.warning(f"Volume down command failed: {result.stderr.strip()}")
                                    else:
                                        logger.debug(f"Volume down command succeeded: {result.stdout.strip()}")
                                except Exception as e:
                                    logger.error(f"Error adjusting volume down: {e}")
                            else:
                                logger.warning("Volume DOWN pressed but no audio control available")
                                # Alternativ könnten wir hier XF86AudioLowerVolume-Taste simulieren
                    elif report_id == 2:
                        if payload == 0x03:
                            logger.info(f"📞 BUTTON: PHONE button pressed (count: {count}) → toggling satellite state")
                            # Verwende die Web-API, um den Satellite zu steuern
                            toggle_satellite_state()
                        else:
                            # Log unbekannte Tasten im Report 2
                            logger.info(f"❓ BUTTON: Unknown button (report_id: {report_id}, payload: {payload:02x}, count: {count})")
                    else:
                        # Log alle anderen unbekannten Tasten
                        logger.info(f"❓ BUTTON: Unknown button (report_id: {report_id}, payload: {payload:02x}, count: {count})")
                    
                # Kurze Pause
                time.sleep(0.05)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Error in reading loop: {e}")
                time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\nExiting...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        # Schließe das Gerät
        if device:
            try:
                if using_hid:
                    device.close()
                else:
                    device.close()
                logger.info("Device closed")
            except Exception as e:
                logger.error(f"Error closing device: {e}")

if __name__ == "__main__":
    main()
