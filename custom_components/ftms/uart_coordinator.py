"""Data coordinator for receiving Sole UART workout data."""

import logging
from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyftms.client import const as c
from sole_uart import SoleClient, WorkoutData

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class UartEvent:
    """Event data structure matching FtmsEvents for sensor compatibility."""

    event_id: str = "update"
    event_data: dict[str, Any] = field(default_factory=dict)


class UartDataCoordinator(DataUpdateCoordinator[UartEvent]):
    """Sole UART workout data coordinator.

    Converts WorkoutData from sole_uart to the same event format
    used by the FTMS coordinator for sensor compatibility.
    """

    def __init__(self, hass: HomeAssistant, client: SoleClient) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self._client = client
        self._hass = hass
        self._update_count = 0

        _LOGGER.debug("UART coordinator initialized, registering callbacks")

        # Register callback for workout data updates
        client.set_workout_data_callback(self._on_workout_data)

        # Register state callback for connection status logging
        client.set_state_callback(self._on_state_change)

    def _on_state_change(self, state) -> None:
        """Log state changes from UART client."""
        _LOGGER.debug("UART state change: %s", state)

    def _on_workout_data(self, data: WorkoutData) -> None:
        """Handle workout data from UART client.

        Maps WorkoutData fields to pyftms property names for sensor compatibility.
        This callback is called from the BLE event loop.
        """
        # Convert WorkoutData to a dict matching pyftms property keys
        event_data: dict[str, Any] = {}

        # Speed (km/h or mph depending on device units)
        if data.speed is not None:
            event_data[c.SPEED_INSTANT] = data.speed

        # Distance (meters - convert from km/miles)
        if data.distance is not None:
            # Assume metric for now, device reports in km
            event_data[c.DISTANCE_TOTAL] = int(data.distance * 1000)

        # Calories -> energy_total
        if data.calories is not None:
            event_data[c.ENERGY_TOTAL] = data.calories

        # Heart rate
        if data.heart_rate is not None and data.heart_rate > 0:
            event_data[c.HEART_RATE] = data.heart_rate

        # Incline -> inclination (this is the key UART advantage!)
        if data.incline is not None:
            event_data[c.INCLINATION] = data.incline

        # Elapsed time in seconds
        if data.minutes is not None and data.seconds is not None:
            event_data[c.TIME_ELAPSED] = data.elapsed_time_seconds

        self._update_count += 1
        _LOGGER.debug(
            "UART workout data #%d: speed=%.1f, incline=%s, distance=%.2f, calories=%s, hr=%s, time=%ss",
            self._update_count,
            data.speed or 0,
            data.incline,
            data.distance or 0,
            data.calories,
            data.heart_rate,
            data.elapsed_time_seconds if data.minutes is not None else "N/A",
        )
        _LOGGER.debug("UART mapped event_data: %s", event_data)

        # Schedule the update in the HA event loop
        self._hass.loop.call_soon_threadsafe(
            self._schedule_update, UartEvent(event_data=event_data)
        )

    @callback
    def _schedule_update(self, event: UartEvent) -> None:
        """Schedule coordinator update from the main thread."""
        self.async_set_updated_data(event)
