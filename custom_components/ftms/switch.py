"""FTMS integration switch platform."""

import logging
from typing import Any, override

from bleak.exc import BleakError
from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.const import STATE_OFF, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import FtmsConfigEntry
from .entity import FtmsEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FtmsConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a FTMS switch entry."""

    connection_switch = ConnectionSwitchEntity(
        entry=entry,
        description=SwitchEntityDescription(
            key="connection",
            device_class=SwitchDeviceClass.SWITCH,
            entity_category=EntityCategory.CONFIG,
        ),
    )

    async_add_entities([connection_switch])


class ConnectionSwitchEntity(FtmsEntity, SwitchEntity, RestoreEntity):
    """Representation of FTMS connection switch.
    
    Controls BLE connection to the fitness machine.
    Defaults to OFF (disconnected) to allow other apps to connect.
    Turn ON to enable HA control and sensor updates.
    """

    @override
    async def async_added_to_hass(self) -> None:
        """Call when the switch is added to hass."""
        # Check actual connection state first
        if self.ftms.is_connected:
            self._attr_is_on = True
            _LOGGER.debug("Device already connected at startup")
        else:
            # Check restored state
            state = await self.async_get_last_state()
            
            # Default to OFF (disconnected) - this allows other apps to use the device
            # Only connect if explicitly turned on previously
            self._attr_is_on = False

            if state is not None and state.state != STATE_OFF:
                # User had it ON before, try to reconnect
                _LOGGER.info(f"Restoring connection to {self.ftms.name}")
                try:
                    await self.ftms.connect()
                    self._attr_is_on = True
                except Exception as e:
                    _LOGGER.warning(f"Failed to restore connection: {e}")
                    self._attr_is_on = False

        await super().async_added_to_hass()

    @property
    def is_on(self) -> bool:
        """Return true if connected."""
        # Sync with actual BLE connection state
        return self.ftms.is_connected

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on - connect to the device."""
        if self.ftms.is_connected:
            _LOGGER.debug("Already connected")
            self._attr_is_on = True
            self.async_write_ha_state()
            return

        try:
            _LOGGER.info(f"Connecting to {self.ftms.name}...")
            await self.ftms.connect()
            self._attr_is_on = True
            _LOGGER.info(f"Connected to {self.ftms.name}")

        except BleakError as e:
            _LOGGER.error(f"Failed to connect: {e}")
            self._attr_is_on = False
        
        self.async_write_ha_state()
        # Notify other entities that connection state changed
        self._data.coordinator.notify_connection_changed()

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off - disconnect from the device."""
        if not self.ftms.is_connected:
            _LOGGER.debug("Already disconnected")
            self._attr_is_on = False
            self.async_write_ha_state()
            return

        _LOGGER.info(f"Disconnecting from {self.ftms.name}...")
        await self.ftms.disconnect()
        self._attr_is_on = False
        _LOGGER.info(f"Disconnected from {self.ftms.name}")
        self.async_write_ha_state()
        # Notify other entities that connection state changed
        self._data.coordinator.notify_connection_changed()

    @property
    @override
    def available(self) -> bool:
        return True

