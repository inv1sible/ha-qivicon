"""Local client for the QIVICON Aurora JSON-RPC API."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import re
import time
from typing import Any
from urllib.parse import quote

from aiohttp import ClientError, ClientSession, ClientTimeout, CookieJar


class QiviconError(Exception):
    """Base QIVICON error."""


class QiviconAuthError(QiviconError):
    """Authentication failed."""


class QiviconConnectionError(QiviconError):
    """The Home Base could not be reached."""


@dataclass(slots=True)
class QiviconSnapshot:
    """Data returned by one coordinator refresh."""

    system: dict[str, Any]
    devices: list[dict[str, Any]]
    items: list[dict[str, Any]]
    rooms: list[dict[str, Any]]


class QiviconClient:
    """Authenticate to and call a QIVICON Home Base."""

    def __init__(
        self,
        host: str,
        password: str,
        *,
        session: ClientSession | None = None,
        verify_ssl: bool = False,
    ) -> None:
        self.host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
        self.password = password
        self.verify_ssl = verify_ssl
        self._external_session = session
        self._session: ClientSession | None = session
        self._access_token: str | None = None
        self._gateway_id: str | None = None
        self._rpc_id = 0
        self._login_lock = asyncio.Lock()

    @property
    def base_url(self) -> str:
        return f"https://{self.host}"

    async def _ensure_session(self) -> ClientSession:
        if self._session is None or self._session.closed:
            self._session = ClientSession(
                cookie_jar=CookieJar(unsafe=True),
                timeout=ClientTimeout(total=30),
            )
        return self._session

    async def close(self) -> None:
        if self._session is not None and self._external_session is None:
            await self._session.close()

    async def login(self) -> None:
        """Create a web session and extract Aurora's API credentials."""
        async with self._login_lock:
            session = await self._ensure_session()
            login_url = f"{self.base_url}/system/http/login"
            target = "/dashboard/system.app.aurora/index.html"
            ssl = None if self.verify_ssl else False
            try:
                async with session.get(
                    login_url, params={"target": target}, ssl=ssl
                ) as response:
                    await response.read()

                now_ms = int(time.time() * 1000)
                form = {
                    "t": str(now_ms),
                    "ts": time.strftime("%a %b %d %Y %H:%M:%S %z"),
                    "f": target,
                    "lb": "",
                    "u": "",
                    "p": self.password,
                    "submit-btn": "",
                }
                async with session.post(
                    login_url,
                    data=form,
                    ssl=ssl,
                    allow_redirects=False,
                ) as response:
                    if response.status != 302:
                        await response.read()
                        raise QiviconAuthError(
                            f"Home Base rejected the device password (HTTP {response.status})"
                        )

                async with session.get(
                    f"{self.base_url}{target}", ssl=ssl
                ) as response:
                    html = await response.text()
                    if response.status != 200 or 'id="login-form"' in html:
                        raise QiviconAuthError("Home Base returned the login page")
            except QiviconAuthError:
                raise
            except (ClientError, asyncio.TimeoutError) as err:
                raise QiviconConnectionError(str(err)) from err

            access_match = re.search(
                r"data-access-token\s*=\s*['\"]([^'\"]+)", html
            )
            attrs = dict(
                re.findall(r"data-([\w-]+)\s*=\s*['\"]([^'\"]*)", html)
            )
            gateway_id = next(
                (value for key, value in attrs.items() if "gateway" in key.lower()),
                None,
            )
            if access_match is None or not gateway_id:
                raise QiviconAuthError("Aurora API credentials were absent from the dashboard")
            self._access_token = access_match.group(1)
            self._gateway_id = gateway_id

    async def _rpc(self, requests: list[dict[str, Any]], *, retry: bool = True) -> list[Any]:
        if self._access_token is None or self._gateway_id is None:
            await self.login()
        session = await self._ensure_session()
        ssl = None if self.verify_ssl else False
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "QIVICON-ServiceGatewayId": str(self._gateway_id),
            "Content-Type": "application/json",
        }
        try:
            async with session.post(
                f"{self.base_url}/remote/json-rpc",
                headers=headers,
                json=requests,
                ssl=ssl,
            ) as response:
                payload = await response.json(content_type=None)
        except (ClientError, asyncio.TimeoutError, json.JSONDecodeError) as err:
            raise QiviconConnectionError(str(err)) from err

        auth_failed = response.status == 401 or any(
            "security ID" in str(entry.get("error", {}).get("message", ""))
            for entry in payload
        )
        if auth_failed and retry:
            self._access_token = None
            self._gateway_id = None
            await self.login()
            return await self._rpc(requests, retry=False)
        if response.status >= 400:
            raise QiviconError(f"JSON-RPC request failed with HTTP {response.status}")
        return payload

    def _rest_request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        self._rpc_id += 1
        headers = {"accept-language": "en-US"}
        if content_type:
            headers["content-type"] = content_type
        if body is not None and not isinstance(body, str):
            body = json.dumps(body, separators=(",", ":"))
        return {
            "jsonrpc": "2.0",
            "method": "smarthome.rest/proxy",
            "id": f"ha-{self._rpc_id}",
            "params": [
                {"method": method, "path": path, "headers": headers, "body": body}
            ],
            "options": "confidential",
        }

    async def rest(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        content_type: str | None = None,
    ) -> Any:
        reply = (await self._rpc([
            self._rest_request(method, path, body=body, content_type=content_type)
        ]))[0]
        if error := reply.get("error"):
            raise QiviconError(error.get("message", str(error)))
        result = reply.get("result", {})
        status = int(result.get("Status", 500))
        if status >= 400:
            raise QiviconError(f"REST {method} {path} failed with status {status}")
        response_body = result.get("Body")
        if response_body in (None, ""):
            return None
        try:
            return json.loads(response_body)
        except (TypeError, json.JSONDecodeError):
            return response_body

    async def rpc_call(self, method: str, params: list[Any]) -> Any:
        """Call a QIVICON JSON-RPC method directly."""
        self._rpc_id += 1
        reply = (await self._rpc([{
            "jsonrpc": "2.0",
            "method": method,
            "id": f"ha-{self._rpc_id}",
            "params": params,
            "options": "confidential",
        }]))[0]
        if error := reply.get("error"):
            raise QiviconError(error.get("message", str(error)))
        return reply.get("result")

    async def get_snapshot(self) -> QiviconSnapshot:
        """Fetch all shared integration data."""
        paths = (
            "/rest/qivicon/system",
            "/rest/qivicon/devices",
            "/rest/items",
            "/rest/qivicon/rooms",
        )
        requests = [self._rest_request("GET", path) for path in paths]
        replies = await self._rpc(requests)
        values: list[Any] = []
        for path, reply in zip(paths, replies, strict=True):
            if error := reply.get("error"):
                raise QiviconError(error.get("message", str(error)))
            result = reply.get("result", {})
            status = int(result.get("Status", 500))
            if status >= 400:
                raise QiviconError(f"GET {path} failed with status {status}")
            body = result.get("Body")
            values.append(json.loads(body) if body else [])
        return QiviconSnapshot(values[0], values[1], values[2], values[3])

    async def send_item_command(self, item_name: str, command: str) -> None:
        """Send an openHAB-style command through the authenticated proxy."""
        path = f"/rest/items/{quote(item_name, safe='')}"
        await self.rest("POST", path, body=command, content_type="text/plain; charset=UTF-8")
