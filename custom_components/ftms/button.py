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
    c.SPEED_UP,
    c.SPEED_DOWN,
    c.INCLINE_UP,
    c.INCLINE_DOWN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FtmsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a FTMS button entry."""

    ftms = entry.runtime_data.ftms
    
    # Get supported settings from stored data (works even when not connected)
    stored_settings = entry.data.get("supported_settings", [])
    
    # Check if this is a Sole device (from stored variant or device name)
    is_sole = (
        entry.data.get("ftms_variant") == "sole" or
        (ftms.name and any(ftms.name.startswith(prefix) for prefix in ("F63", "F65", "F80", "F85", "F89", "S77", "TT8", "ST90", "TRX")))
    )
    
    # Build list of supported buttons
    supported = set(stored_settings)
    
    # Basic control buttons (start, stop, pause, reset) are always available
    # for any fitness machine - they're fundamental FTMS controls
    supported.update([c.START, c.STOP, c.PAUSE, c.RESET])
    
    if is_sole:
        # Add Sole-specific incremental controls
        supported.update([c.SPEED_UP, c.SPEED_DOWN, c.INCLINE_UP, c.INCLINE_DOWN])

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

        elif self.key == c.SPEED_UP:
            await self.ftms.speed_up()

        elif self.key == c.SPEED_DOWN:
            await self.ftms.speed_down()

        elif self.key == c.INCLINE_UP:
            await self.ftms.incline_up()

        elif self.key == c.INCLINE_DOWN:
            await self.ftms.incline_down()
