"""The FTMS integration."""

import logging

import pyftms
from bleak.exc import BleakError
from homeassistant.components import bluetooth
from homeassistant.components.bluetooth.match import BluetoothCallbackMatcher
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_ADDRESS,
    CONF_SENSORS,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .coordinator import DataCoordinator
from .models import FtmsData

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

_LOGGER = logging.getLogger(__name__)

type FtmsConfigEntry = ConfigEntry[FtmsData]


async def async_unload_entry(hass: HomeAssistant, entry: FtmsConfigEntry) -> bool:
    """Unload a config entry."""

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        try:
            await entry.runtime_data.ftms.disconnect()
        except Exception as e:
            _LOGGER.debug("Error disconnecting during unload: %s", e)
        bluetooth.async_rediscover_address(hass, entry.runtime_data.ftms.address)

    return unload_ok


async def async_setup_entry(hass: HomeAssistant, entry: FtmsConfigEntry) -> bool:
    """Set up device from a config entry."""

    address: str = entry.data[CONF_ADDRESS]

    if not (srv_info := bluetooth.async_last_service_info(hass, address)):
        raise ConfigEntryNotReady(translation_key="device_not_found")

    def _on_disconnect(ftms_: pyftms.FitnessMachine) -> None:
        """Disconnect handler. Reload entry on disconnect."""

        if ftms_.need_connect:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    try:
        ftms = pyftms.get_client(
            srv_info.device,
            srv_info.advertisement,
            on_disconnect=_on_disconnect,
        )

    except pyftms.NotFitnessMachineError:
        raise ConfigEntryNotReady(translation_key="ftms_error")

    coordinator = DataCoordinator(hass, ftms)

    # Use stored device info from config entry (set during config flow)
    # This avoids needing to connect on every HA restart
    stored_device_info = entry.data.get("device_info", {})

    if stored_device_info:
        _LOGGER.debug("Using stored device info: %s", stored_device_info)
        _LOGGER.debug("Stored machine type: %s", entry.data.get("machine_type"))
        _LOGGER.debug("Stored protocol variant: %s", entry.data.get("protocol_variant"))
        _LOGGER.debug("Stored available properties: %s", entry.data.get("available_properties"))
        _LOGGER.debug("Stored supported settings: %s", entry.data.get("supported_settings"))

        # Don't auto-connect - let the connection switch control this
        # This allows other apps (Sole app, Zwift) to connect when HA isn't actively using it
    else:
        # Legacy entry without stored device info - need to connect once to get it
        _LOGGER.warning("No stored device info, connecting to read it (one-time migration)")
        try:
            await ftms.connect()
            stored_device_info = ftms.device_info

            # Update config entry with device info for future use
            new_data = {
                **entry.data,
                "device_info": ftms.device_info,
                "machine_type": ftms.machine_type.name,
                "protocol_variant": ftms.protocol_variant,
                "available_properties": list(ftms.available_properties),
                "supported_settings": list(ftms.supported_settings),
            }
            hass.config_entries.async_update_entry(entry, data=new_data)

            # Disconnect after reading info
            await ftms.disconnect()

        except BleakError as exc:
            raise ConfigEntryNotReady(translation_key="connection_failed") from exc

    _LOGGER.debug("Device Information: %s", stored_device_info)

    unique_id = "".join(
        x for x in stored_device_info.get("serial_number", address) if x.isalnum()
    ).lower()

    _LOGGER.debug("Registered FTMS device. UniqueID is '%s'. Connection switch controls BLE connection.", unique_id)

    device_info = dr.DeviceInfo(
        connections={(dr.CONNECTION_BLUETOOTH, ftms.address)},
        identifiers={(DOMAIN, unique_id)},
        translation_key=entry.data.get("machine_type", "treadmill").lower(),
        **stored_device_info,
    )

    entry.runtime_data = FtmsData(
        entry_id=entry.entry_id,
        unique_id=unique_id,
        device_info=device_info,
        ftms=ftms,
        coordinator=coordinator,
        sensors=entry.options[CONF_SENSORS],
    )

    @callback
    def _async_on_ble_event(
        srv_info: bluetooth.BluetoothServiceInfoBleak,
        change: bluetooth.BluetoothChange,
    ) -> None:
        """Update from a ble callback."""

        ftms.set_ble_device_and_advertisement_data(
            srv_info.device, srv_info.advertisement
        )

    entry.async_on_unload(
        bluetooth.async_register_callback(
            hass,
            _async_on_ble_event,
            BluetoothCallbackMatcher(address=address),
            bluetooth.BluetoothScanningMode.ACTIVE,
        )
    )

    # Platforms initialization
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_entry_update_handler))

    async def _async_hass_stop_handler(event: Event) -> None:
        """Close the connection."""

        await ftms.disconnect()

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_hass_stop_handler)
    )

    return True


async def _async_entry_update_handler(
    hass: HomeAssistant, entry: FtmsConfigEntry
) -> None:
    """Options update handler."""

    if entry.options[CONF_SENSORS] != entry.runtime_data.sensors:
        hass.config_entries.async_schedule_reload(entry.entry_id)
