"""Async HTTP client for interacting with Harbor REST endpoints."""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

import aiohttp


class HarborAPIError(RuntimeError):
    """Raised when Harbor responds with an error status code."""

    def __init__(self, message: str, status: int, payload: Any | None = None):
        super().__init__(message)
        self.status = status
        self.payload = payload

    def to_response(self) -> Dict[str, Any]:
        response: Dict[str, Any] = {"error": {"message": str(self)}}
        if self.payload is not None:
            response["error"]["payload"] = self.payload
        return response


class HarborAPI:
    """Thin asynchronous wrapper around Harbor's REST and xnode endpoints."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        rest_base: str,
        rest_api_path: str = "",
        api_key: str | None,
        request_timeout: Optional[int] = None,
        xnode_base: Optional[str] = None,
        xnode_api_path: str = "",
    ) -> None:
        self._session = session
        self._rest_base = rest_base.rstrip("/")
        self._rest_api_path = rest_api_path.rstrip("/")
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=request_timeout) if request_timeout else None
        self._xnode_base = xnode_base.rstrip("/") if xnode_base else None
        self._xnode_api_path = xnode_api_path.rstrip("/") if xnode_api_path else ""

    async def close(self) -> None:
        if not self._session.closed:
            await self._session.close()

    async def get_markets(self) -> Dict[str, Any]:
        return await self._request("GET", "/markets")

    async def get_account(self) -> Dict[str, Any]:
        return await self._request("GET", "/account")

    async def get_depth(self, symbol: str, depth: Optional[int] = None) -> Dict[str, Any]:
        params = {"depth": depth} if depth is not None else None
        return await self._request("POST", f"/depth/{symbol}", params=params)

    async def create_order(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/order", json_payload=dict(payload))

    async def update_order(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("PUT", "/order", json_payload=dict(payload))

    async def cancel_order(self, query: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("DELETE", "/order", params=dict(query))

    async def get_order(self, query: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("GET", "/order", params=dict(query))

    async def get_orders(self, query: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("GET", "/orders", params=dict(query))

    async def withdraw(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        return await self._request("POST", "/withdraw", json_payload=dict(payload))

    async def get_withdraw(self, withdraw_id: str) -> Dict[str, Any]:
        return await self._request("GET", f"/withdraw/{withdraw_id}")

    async def get_inbound_addresses(self) -> Dict[str, Any]:
        return await self._request_xnode("GET", "/inbound_addresses")

    async def get_outbound_fees(self) -> Dict[str, Any]:
        return await self._request_xnode("GET", "/outbound_fees")

    async def get_tx_details(self, tx_id: str) -> Dict[str, Any]:
        return await self._request_xnode("GET", f"/tx/details/{tx_id}")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_payload: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if not path.startswith("/"):
            path = f"/{path}"
        url = self._compose_url(self._rest_base, self._rest_api_path, path)
        headers = {"accept": "application/json"}
        if self._api_key:
            headers["X-API-KEY"] = self._api_key

        return await self._send_request(url, method, headers, params, json_payload)

    async def _request_xnode(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json_payload: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if self._xnode_base is None:
            raise HarborAPIError("xnode base URL is not configured", status=500)
        if not path.startswith("/"):
            path = f"/{path}"
        url = self._compose_url(self._xnode_base, self._xnode_api_path, path)
        headers = {"accept": "application/json"}
        return await self._send_request(url, method, headers, params, json_payload)

    async def _send_request(
        self,
        url: str,
        method: str,
        headers: Mapping[str, str],
        params: Optional[Mapping[str, Any]],
        json_payload: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        try:
            async with self._session.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json_payload,
                timeout=self._timeout,
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                raw_text = await response.text()
                data: Any
                if "application/json" in content_type:
                    if raw_text:
                        data = json.loads(raw_text)
                    else:
                        data = {}
                else:
                    data = raw_text

                if response.status >= 400:
                    raise HarborAPIError(
                        f"Harbor request failed with status {response.status}",
                        status=response.status,
                        payload=data,
                    )
                if not isinstance(data, dict):
                    return {"result": data}
                return data
        except HarborAPIError:
            raise
        except aiohttp.ClientError as exc:
            raise HarborAPIError(f"Network error: {exc}", status=503) from exc

    @staticmethod
    def _compose_url(base: str, api_path: str, path: str) -> str:
        parts = [base]
        if api_path:
            parts.append(api_path.lstrip("/"))
        parts.append(path.lstrip("/"))
        return "/".join(part.strip("/") for part in parts if part)
