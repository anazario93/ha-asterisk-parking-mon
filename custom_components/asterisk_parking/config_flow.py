"""Config and options flows for Asterisk Parking Monitor."""
from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_PARKINGLOT, CONF_SLOT_END, CONF_SLOT_START, DEFAULT_PARKINGLOT,
    DEFAULT_PORT, DEFAULT_SLOT_END, DEFAULT_SLOT_START, DOMAIN, MAX_SLOT_COUNT,
)


async def _test_ami(data: dict[str, Any]) -> None:
    """Test AMI TCP access and credentials."""
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(data[CONF_HOST], int(data[CONF_PORT])), timeout=5
        )
        await asyncio.wait_for(reader.readline(), timeout=5)
        writer.write(
            (
                "Action: Login\r\n"
                f"Username: {data[CONF_USERNAME]}\r\n"
                f"Secret: {data[CONF_PASSWORD]}\r\n"
                "Events: off\r\n\r\n"
            ).encode()
        )
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5)
        if b"Response: Success" not in response:
            raise CannotConnect
        writer.write(b"Action: Logoff\r\n\r\n")
        await writer.drain()
    except (
        OSError, asyncio.TimeoutError, asyncio.IncompleteReadError,
        asyncio.LimitOverrunError, ValueError,
    ) as err:
        raise CannotConnect from err
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except OSError:
                pass


class CannotConnect(HomeAssistantError):
    """Error connecting to AMI."""


def _validate_range(start: int, end: int) -> str | None:
    """Validate inclusive slot range."""
    if start < 1 or end < start:
        return "invalid_range"
    if end - start + 1 > MAX_SLOT_COUNT:
        return "range_too_large"
    return None


def _schema(current: dict[str, Any]) -> vol.Schema:
    """Build form schema with defaults."""
    return vol.Schema({
        vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
        vol.Required(CONF_PORT, default=current.get(CONF_PORT, DEFAULT_PORT)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
        vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")): str,
        vol.Optional(
            CONF_PARKINGLOT,
            default=current.get(CONF_PARKINGLOT, DEFAULT_PARKINGLOT),
        ): str,
        vol.Required(
            CONF_SLOT_START,
            default=current.get(CONF_SLOT_START, DEFAULT_SLOT_START),
        ): vol.Coerce(int),
        vol.Required(
            CONF_SLOT_END,
            default=current.get(CONF_SLOT_END, DEFAULT_SLOT_END),
        ): vol.Coerce(int),
    })


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Configure AMI and the parking range."""
        errors: dict[str, str] = {}
        if user_input is not None:
            range_error = _validate_range(
                int(user_input[CONF_SLOT_START]), int(user_input[CONF_SLOT_END])
            )
            if range_error:
                errors["base"] = range_error
            else:
                try:
                    await _test_ami(user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(
                        f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}:{user_input[CONF_USERNAME]}"
                    )
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"Asterisk Parking ({user_input[CONF_HOST]})",
                        data=user_input,
                    )
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the options flow."""
        return OptionsFlow(config_entry)


class OptionsFlow(config_entries.OptionsFlow):
    """Allow changing credentials and parking range."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Edit settings."""
        current = {**self._entry.data, **self._entry.options}
        errors: dict[str, str] = {}
        if user_input is not None:
            range_error = _validate_range(
                int(user_input[CONF_SLOT_START]), int(user_input[CONF_SLOT_END])
            )
            if range_error:
                errors["base"] = range_error
            else:
                try:
                    await _test_ami(user_input)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init", data_schema=_schema(current), errors=errors
        )
