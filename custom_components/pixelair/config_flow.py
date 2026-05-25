"""Config flow for the PixelAir integration.

This module handles the configuration flow for adding PixelAir devices
to Home Assistant. It supports automatic device discovery on the
local network via UDP broadcast, as well as DHCP-triggered discovery.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from libpixelair import DiscoveredDevice, DiscoveryService, UDPListener
import voluptuous as vol

from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_NAME

from .const import (
    CONF_MAC_ADDRESS,
    CONF_SERIAL_NUMBER,
    DISCOVERY_TIMEOUT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class PixelAirConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PixelAir.

    This config flow discovers PixelAir devices on the local network
    and allows the user to select and add them to Home Assistant.
    """

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_device: DiscoveredDevice | None = None
        self._discovered_devices: dict[str, DiscoveredDevice] = {}
        self._listener: UDPListener | None = None
        self._dhcp_discovery_info: DhcpServiceInfo | None = None

    async def async_step_dhcp(
        self, discovery_info: DhcpServiceInfo
    ) -> ConfigFlowResult:
        """Handle DHCP discovery of an ESP32 device.

        When DHCP detects an ESP32 device on the network, this step
        probes it via UDP to check if it's a PixelAir device.

        Args:
            discovery_info: DHCP discovery information containing IP and MAC.

        Returns:
            The next step in the flow or abort if not a PixelAir device.
        """
        _LOGGER.debug(
            "DHCP discovery triggered for %s (%s)",
            discovery_info.ip,
            discovery_info.macaddress,
        )

        # Normalize MAC address for unique_id
        mac_address = discovery_info.macaddress.lower().replace(":", "")

        # Check if this device is already configured
        await self.async_set_unique_id(mac_address)
        self._abort_if_unique_id_configured(updates={"ip": discovery_info.ip})

        # Store DHCP info for later use
        self._dhcp_discovery_info = discovery_info

        # Probe the device via UDP to confirm it's a PixelAir device
        try:
            listener = await self._get_listener()
            discovery = DiscoveryService(listener)

            # Send targeted discovery to the specific IP
            device = await discovery.verify_device(
                ip_address=discovery_info.ip,
                timeout=5.0,
            )

            if device is None:
                # Device didn't respond to PixelAir protocol
                _LOGGER.debug(
                    "Device at %s is not a PixelAir device", discovery_info.ip
                )
                await self._cleanup_listener()
                return self.async_abort(reason="not_pixelair_device")

            # Get full device info (model, MAC, etc.)
            device = await discovery.get_device_info(device, timeout=5.0)
            await self._cleanup_listener()

            # Verify MAC address matches
            if device.mac_address:
                device_mac = device.mac_address.lower().replace(":", "")
                if device_mac != mac_address:
                    _LOGGER.debug(
                        "MAC mismatch: expected %s, got %s",
                        mac_address,
                        device_mac,
                    )
                    return self.async_abort(reason="not_pixelair_device")

            self._discovered_device = device
            _LOGGER.info(
                "DHCP discovery confirmed PixelAir device: %s at %s",
                device.display_name,
                discovery_info.ip,
            )
            return await self.async_step_confirm()

        except asyncio.TimeoutError:
            _LOGGER.debug(
                "Timeout probing device at %s", discovery_info.ip
            )
            await self._cleanup_listener()
            return self.async_abort(reason="not_pixelair_device")
        except Exception as err:
            _LOGGER.debug(
                "Error probing device at %s: %s", discovery_info.ip, err
            )
            await self._cleanup_listener()
            return self.async_abort(reason="not_pixelair_device")

    async def _get_listener(self) -> UDPListener:
        """Get or create a UDP listener for discovery.

        Returns:
            The UDP listener instance.
        """
        if self._listener is None:
            self._listener = UDPListener()
            await self._listener.start()
        return self._listener

    async def _cleanup_listener(self) -> None:
        """Clean up the UDP listener."""
        if self._listener is not None:
            await self._listener.stop()
            self._listener = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle user-initiated setup.

        This is the first step when a user adds the integration.
        It prompts the user to start device discovery.

        Args:
            user_input: User input from the form (if submitted).

        Returns:
            The next step in the flow.
        """
        if user_input is not None:
            return await self.async_step_discovery()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
        )

    async def async_step_discovery(
        self, _user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device discovery.

        Discovers PixelAir devices on the network and determines
        the next step based on how many devices are found.

        Args:
            _user_input: Not used in this step.

        Returns:
            The next step in the flow.
        """
        errors: dict[str, str] = {}

        try:
            listener = await self._get_listener()
            discovery = DiscoveryService(listener)

            # Discover devices with full info
            devices = await discovery.discover_with_info(
                timeout=DISCOVERY_TIMEOUT,
                state_timeout=DISCOVERY_TIMEOUT,
            )
            await self._cleanup_listener()

            if not devices:
                return self.async_abort(reason="no_devices_found")

            # Filter out already configured devices
            new_devices: list[DiscoveredDevice] = []
            for device in devices:
                if device.mac_address:
                    # Normalize MAC address (lowercase, no colons)
                    normalized_mac = device.mac_address.lower().replace(":", "")
                    await self.async_set_unique_id(normalized_mac)
                    existing = self._async_current_entries()
                    is_configured = any(
                        entry.unique_id == normalized_mac
                        for entry in existing
                    )
                    if not is_configured:
                        new_devices.append(device)

            if not new_devices:
                return self.async_abort(reason="all_devices_configured")

            # If only one device, go directly to confirmation
            if len(new_devices) == 1:
                self._discovered_device = new_devices[0]
                normalized_mac = self._discovered_device.mac_address.lower().replace(
                    ":", ""
                )
                await self.async_set_unique_id(normalized_mac)
                self._abort_if_unique_id_configured()
                return await self.async_step_confirm()

            # Multiple devices - store them and let user select
            self._discovered_devices = {
                device.serial_number: device for device in new_devices
            }
            return await self.async_step_select_device()

        except Exception as err:
            _LOGGER.exception("Error during discovery: %s", err)
            await self._cleanup_listener()
            errors["base"] = "cannot_connect"
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({}),
                errors=errors,
            )

    async def async_step_select_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle device selection when multiple devices are found.

        Args:
            user_input: User's device selection (if submitted).

        Returns:
            The next step in the flow.
        """
        if user_input is not None:
            serial = user_input.get("device")
            self._discovered_device = self._discovered_devices.get(serial)

            if self._discovered_device is None:
                return self.async_abort(reason="device_not_found")

            normalized_mac = self._discovered_device.mac_address.lower().replace(
                ":", ""
            )
            await self.async_set_unique_id(normalized_mac)
            self._abort_if_unique_id_configured()
            return await self.async_step_confirm()

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        device_options = {
            device.serial_number: f"{device.display_name} ({device.ip_address})"
            for device in self._discovered_devices.values()
        }

        return self.async_show_form(
            step_id="select_device",
            data_schema=vol.Schema(
                {
                    vol.Required("device"): vol.In(device_options),
                }
            ),
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the discovered device.

        Args:
            user_input: User confirmation (if submitted).

        Returns:
            The config entry creation or confirmation form.
        """
        if self._discovered_device is None:
            return self.async_abort(reason="device_not_found")

        if user_input is not None:
            # Normalize MAC address (lowercase, no colons)
            normalized_mac = self._discovered_device.mac_address.lower().replace(
                ":", ""
            )
            return self.async_create_entry(
                title=self._discovered_device.display_name,
                data={
                    CONF_NAME: self._discovered_device.display_name,
                    CONF_MAC_ADDRESS: normalized_mac,
                    CONF_SERIAL_NUMBER: self._discovered_device.serial_number,
                },
            )

        return self.async_show_form(
            step_id="confirm",
            description_placeholders={
                "name": self._discovered_device.display_name,
                "model": self._discovered_device.model or "PixelAir",
                "serial": self._discovered_device.serial_number,
                "ip": self._discovered_device.ip_address,
            },
        )
