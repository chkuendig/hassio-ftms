"""Data coordinator for receiving FTMS events."""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pyftms import FitnessMachine, FtmsEvents

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DataCoordinator(DataUpdateCoordinator[FtmsEvents]):
    """FTMS events coordinator."""

    def __init__(self, hass: HomeAssistant, ftms: FitnessMachine) -> None:
        """Initialize the coordinator."""
        self._ftms = ftms

        def _on_ftms_event(data: FtmsEvents):
            _LOGGER.debug(f"Event data: {data}")
            self.async_set_updated_data(data)

        super().__init__(hass, _LOGGER, name=DOMAIN)

        ftms.set_callback(_on_ftms_event)

    def notify_connection_changed(self) -> None:
        """Notify all listeners that connection state changed."""
        _LOGGER.debug("Connection state changed, notifying listeners")
        self.async_set_updated_data(self.data)
