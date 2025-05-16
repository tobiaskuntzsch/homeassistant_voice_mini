#!/usr/bin/env python3
"""Controls a WS2812B LED strip for Wyoming events."""
import argparse
import asyncio
import logging
import time
from functools import partial
from typing import Tuple

import board
import neopixel
from wyoming.asr import Transcript
from wyoming.event import Event
from wyoming.satellite import (
    RunSatellite,
    SatelliteConnected,
    SatelliteDisconnected,
    StreamingStarted,
    StreamingStopped,
)
from wyoming.server import AsyncEventHandler, AsyncServer
from wyoming.vad import VoiceStarted
from wyoming.wake import Detection

_LOGGER = logging.getLogger()

# WS2812B LED strip configuration
LED_ORDER = neopixel.GRB  # Most WS2812B LEDs use GRB color order
# Default values will be overridden by command line arguments

async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--led-brightness",
        type=float,
        default=0.5,
        help="LED brightness (float from 0.0 to 1.0)",
    )
    parser.add_argument(
        "--num-leds",
        type=int,
        default=1,
        help="Number of LEDs in the strip",
    )
    parser.add_argument(
        "--pin",
        type=int,
        default=18,
        help="GPIO pin number for the LED strip (default: 18, which is D18)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    _LOGGER.debug(args)

    _LOGGER.info("Ready")

    # Initialize the NeoPixel LED strip
    # Convert pin number to board pin
    led_pin = getattr(board, f"D{args.pin}")
    _LOGGER.info(f"Initializing {args.num_leds} LEDs on pin D{args.pin}")
    
    pixels = neopixel.NeoPixel(
        led_pin, 
        args.num_leds, 
        brightness=args.led_brightness, 
        auto_write=False,
        pixel_order=LED_ORDER
    )

    # Start server
    server = AsyncServer.from_uri(args.uri)

    try:
        await server.run(partial(LEDsEventHandler, args, pixels))
    except KeyboardInterrupt:
        pass
    finally:
        # Turn off LEDs
        pixels.fill((0, 0, 0))
        pixels.show()


# -----------------------------------------------------------------------------

_BLACK = (0, 0, 0)
_WHITE = (255, 255, 255)
_RED = (255, 0, 0)
_YELLOW = (255, 255, 0)
_BLUE = (0, 0, 255)
_GREEN = (0, 255, 0)


class LEDsEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        cli_args: argparse.Namespace,
        pixels: neopixel.NeoPixel,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.client_id = str(time.monotonic_ns())
        self.pixels = pixels

        _LOGGER.debug("Client connected: %s", self.client_id)

    async def handle_event(self, event: Event) -> bool:
        _LOGGER.debug(event)

        if StreamingStarted.is_type(event.type):
            self.color(_YELLOW)
        elif Detection.is_type(event.type):
            self.color(_BLUE)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif VoiceStarted.is_type(event.type):
            self.color(_YELLOW)
        elif Transcript.is_type(event.type):
            self.color(_GREEN)
            await asyncio.sleep(1.0)  # show for 1 sec
        elif StreamingStopped.is_type(event.type):
            self.color(_BLACK)
        elif RunSatellite.is_type(event.type):
            self.color(_BLACK)
        elif SatelliteConnected.is_type(event.type):
            # Flash
            for _ in range(3):
                self.color(_GREEN)
                await asyncio.sleep(0.3)
                self.color(_BLACK)
                await asyncio.sleep(0.3)
        elif SatelliteDisconnected.is_type(event.type):
            self.color(_RED)

        return True

    def color(self, rgb: Tuple[int, int, int]) -> None:
        """Set all LEDs to the specified RGB color."""
        self.pixels.fill(rgb)
        self.pixels.show()


# -----------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(main())