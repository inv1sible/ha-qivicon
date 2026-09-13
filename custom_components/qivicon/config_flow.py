"""Config flow for QIVICON."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD

from .api import QiviconAuthError, QiviconClient, QiviconConnectionError, QiviconError
from .const import DOMAIN


class QiviconConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a QIVICON Home Base."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            client = QiviconClient(
                user_input[CONF_HOST],
                user_input[CONF_PASSWORD],
                verify_ssl=False,
            )
            try:
                system = await client.rest("GET", "/rest/qivicon/system")
            except QiviconAuthError:
                errors["base"] = "invalid_auth"
            except QiviconConnectionError:
                errors["base"] = "cannot_connect"
            except QiviconError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_HOST].lower())
                self._abort_if_unique_id_configured()
                title = system.get("label") or "QIVICON"
                return self.async_create_entry(title=title, data=user_input)
            finally:
                await client.close()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
