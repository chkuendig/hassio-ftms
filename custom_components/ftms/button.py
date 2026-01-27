"""FTMS integration button platform."""

import logging
from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from pyftms.client import const as c

from . import FtmsConfigEntry
from .entity import FtmsEntity

_LOGGER = logging.getLogger(__name__)

_ENTITIES = (
    c.RESET,
    c.STOP,
    c.START,
    c.PAUSE,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FtmsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a FTMS button entry."""

    ftms = entry.runtime_data.ftms

    # Get supported settings from ftms instance
    # Devices without FTMS Control Point support return empty tuple
    supported = set(ftms.supported_settings)

    # Basic control buttons (start, stop, pause, reset) are available
    # only for devices that support FTMS Control Point
    if supported:
        supported.update([c.START, c.STOP, c.PAUSE, c.RESET])

    _LOGGER.debug("Creating button entities for: %s", supported)

    entities = [
        FtmsButtonEntity(
            entry=entry,
            description=ButtonEntityDescription(key=key),
        )
        for key in _ENTITIES
        if key in supported
    ]

    async_add_entities(entities)


class FtmsButtonEntity(FtmsEntity, ButtonEntity):
    """Representation of FTMS control buttons."""

    @override
    async def async_press(self) -> None:
        """Handle the button press."""
        if self.key == c.RESET:
            await self.ftms.reset()

        elif self.key == c.START:
            await self.ftms.start_resume()

        elif self.key == c.STOP:
            await self.ftms.stop()

        elif self.key == c.PAUSE:
            await self.ftms.pause()
