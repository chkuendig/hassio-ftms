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
        await entry.runtime_data.ftms.disconnect()
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

    # Use stored machine_type from config instead of re-reading from advertisement
    # This avoids re-triggering Unknown detection for devices like Sole treadmills
    stored_machine_type = entry.data.get("machine_type")
    if stored_machine_type:
        machine_type = pyftms.MachineType[stored_machine_type]
    else:
        # Fallback for old config entries without stored machine_type
        try:
            machine_type = pyftms.get_machine_type_from_service_data(srv_info.advertisement)
        except pyftms.NotFitnessMachineError:
            raise ConfigEntryNotReady(translation_key="ftms_error")

    ftms = pyftms.get_client(
        srv_info.device,
        machine_type,
        on_disconnect=_on_disconnect,
    )

    coordinator = DataCoordinator(hass, ftms)

    try:
        await ftms.connect()

    except BleakError as exc:
        raise ConfigEntryNotReady(translation_key="connection_failed") from exc

    assert ftms.machine_type.name

    _LOGGER.debug(f"Device Information: {ftms.device_info}")
    _LOGGER.debug(f"Machine type: {ftms.machine_type.name}")
    _LOGGER.debug(f"Available sensors: {ftms.available_properties}")
    _LOGGER.debug(f"Supported settings: {ftms.supported_settings}")
    _LOGGER.debug(f"Supported ranges: {ftms.supported_ranges}")

    unique_id = "".join(
        x for x in ftms.device_info.get("serial_number", address) if x.isalnum()
    ).lower()

    _LOGGER.debug(f"Registered new FTMS device. UniqueID is '{unique_id}'.")

    # Filter device_info to only include valid HA DeviceInfo fields
    # (pyftms may include extra fields like fw_version, system_id that HA doesn't accept)
    valid_ha_fields = {"manufacturer", "model", "serial_number", "sw_version", "hw_version"}
    filtered_device_info = {k: v for k, v in ftms.device_info.items() if k in valid_ha_fields}

    device_info = dr.DeviceInfo(
        connections={(dr.CONNECTION_BLUETOOTH, ftms.address)},
        identifiers={(DOMAIN, unique_id)},
        translation_key=ftms.machine_type.name.lower(),
        **filtered_device_info,
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
