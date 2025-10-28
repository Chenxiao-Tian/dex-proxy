from __future__ import annotations

import os
from typing import Any, Dict, Optional

import aiohttp

from pantheon import Pantheon

from py_dex_common.dexes.dex_common import DexCommon
from py_dex_common.web_server import WebServer

from .harbor_api import HarborAPI, HarborAPIError


class Harbor(DexCommon):
    """DexCommon adapter that proxies Harbor's HTTP API."""

    CHANNELS: list[str] = []

    def __init__(self, pantheon: Pantheon, config: dict, server: WebServer, event_sink):
        super().__init__(pantheon, config, server, event_sink)

        harbor_cfg = config['connectors']['harbor']
        rest_cfg = harbor_cfg['rest']
        xnode_cfg = harbor_cfg.get('xnode', {})

        self._rest_base = rest_cfg['base_uri']
        self._rest_api_path = rest_cfg.get('api_path', '')
        self._request_timeout = rest_cfg.get('request_timeout')
        self._session_timeout = rest_cfg.get('session_timeout', self._request_timeout)

        self._xnode_base = xnode_cfg.get('base_uri')
        self._xnode_api_path = xnode_cfg.get('api_path', '')

        self._websocket_url = harbor_cfg.get('websocket', {}).get('url')

        self._api_key_env = harbor_cfg.get('api_key_env', 'HARBOR_API_KEY')
        self._eth_from_addr_env = harbor_cfg.get('eth_from_addr_env', 'ETH_FROM_ADDR')
        self._btc_from_addr_env = harbor_cfg.get('btc_from_addr_env', 'BTC_FROM_ADDR')
        self._configured_api_key = harbor_cfg.get('api_key')
        from_addresses_cfg = harbor_cfg.get('from_addresses', {})
        self._configured_from_addresses = {
            'ETH': from_addresses_cfg.get('ETH'),
            'BTC': from_addresses_cfg.get('BTC'),
        }

        self._session: Optional[aiohttp.ClientSession] = None
        self._api: Optional[HarborAPI] = None
        self._from_addresses: Dict[str, Optional[str]] = {}

        self._register_endpoints(server)

    def _register_endpoints(self, server: WebServer) -> None:
        oapi_targets = ['harbor']
        server.register(
            'GET',
            '/public/harbor/markets',
            self._get_markets,
            summary='List Harbor markets',
            tags=['public', 'harbor'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/public/harbor/depth',
            self._get_depth,
            summary='Get order book depth for a symbol',
            tags=['public', 'harbor'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/private/harbor/account',
            self._get_account,
            summary='Fetch account balances',
            tags=['private', 'harbor'],
            oapi_in=oapi_targets,
        )
        server.register(
            'POST',
            '/private/harbor/order',
            self._create_order,
            summary='Create Harbor order',
            tags=['private', 'harbor', 'orders'],
            oapi_in=oapi_targets,
        )
        server.register(
            'PUT',
            '/private/harbor/order',
            self._update_order,
            summary='Update Harbor order',
            tags=['private', 'harbor', 'orders'],
            oapi_in=oapi_targets,
        )
        server.register(
            'DELETE',
            '/private/harbor/order',
            self._cancel_order,
            summary='Cancel Harbor order',
            tags=['private', 'harbor', 'orders'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/private/harbor/order',
            self._get_order,
            summary='Get a specific Harbor order',
            tags=['private', 'harbor', 'orders'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/private/harbor/orders',
            self._get_orders,
            summary='List Harbor orders',
            tags=['private', 'harbor', 'orders'],
            oapi_in=oapi_targets,
        )
        server.register(
            'POST',
            '/private/harbor/withdraw',
            self._withdraw,
            summary='Create Harbor withdraw request',
            tags=['private', 'harbor', 'funds'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/private/harbor/withdraw',
            self._get_withdraw,
            summary='Fetch Harbor withdrawal status',
            tags=['private', 'harbor', 'funds'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/public/harbor/inbound-addresses',
            self._get_inbound_addresses,
            summary='Retrieve Harbor inbound vault addresses',
            tags=['public', 'harbor', 'funds'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/public/harbor/outbound-fees',
            self._get_outbound_fees,
            summary='Retrieve Harbor outbound fee schedule',
            tags=['public', 'harbor', 'funds'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/public/harbor/tx-details',
            self._get_tx_details,
            summary='Fetch base layer transaction details for Harbor operations',
            tags=['public', 'harbor'],
            oapi_in=oapi_targets,
        )
        server.register(
            'GET',
            '/public/harbor/deposit-instructions',
            self._get_deposit_instructions,
            summary='Provide Harbor deposit instructions including whitelisted from addresses',
            tags=['public', 'harbor', 'funds'],
            oapi_in=oapi_targets,
        )

    async def start(self, private_key):
        await super().start(private_key)

        timeout = aiohttp.ClientTimeout(total=self._session_timeout) if self._session_timeout else None
        if self._api is not None:
            await self._api.close()
            self._api = None
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = aiohttp.ClientSession(timeout=timeout)

        api_key = self._configured_api_key or os.getenv(self._api_key_env)
        if not api_key:
            self._logger.warning('Environment variable %s is not set; authenticated Harbor requests will fail.',
                                 self._api_key_env)

        self._api = HarborAPI(
            self._session,
            rest_base=self._rest_base,
            rest_api_path=self._rest_api_path,
            api_key=api_key,
            request_timeout=self._request_timeout,
            xnode_base=self._xnode_base,
            xnode_api_path=self._xnode_api_path,
        )

        self._from_addresses = {
            'ETH': self._configured_from_addresses.get('ETH') or os.getenv(self._eth_from_addr_env),
            'BTC': self._configured_from_addresses.get('BTC') or os.getenv(self._btc_from_addr_env),
        }

        self.started = True

    async def stop(self) -> None:
        await super().stop()

        if self._api is not None:
            await self._api.close()
            self._api = None

        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def on_new_connection(self, ws):
        return

    async def process_request(self, ws, request_id, method, params: dict):
        return False

    async def _approve(self, request, gas_price_wei, nonce=None):
        raise NotImplementedError('Token approvals are not supported for Harbor integration')

    async def _transfer(self, request, gas_price_wei, nonce=None):
        raise NotImplementedError('Transfers through DexCommon are not supported for Harbor integration')

    async def _amend_transaction(self, request, params, gas_price_wei):
        raise NotImplementedError('Transaction amendments are not supported for Harbor integration')

    async def _cancel_transaction(self, request, gas_price_wei):
        raise NotImplementedError('Transaction cancellation is not supported for Harbor integration')

    async def get_transaction_receipt(self, request, tx_hash):
        return None

    def _get_gas_price(self, request, priority_fee=None):
        return None

    async def on_request_status_update(self, client_request_id, request_status, tx_receipt: dict,
                                        mined_tx_hash: str = None):
        return await super().on_request_status_update(client_request_id, request_status, tx_receipt, mined_tx_hash)

    async def _get_all_open_requests(self, path, params, received_at_ms):
        return 200, []

    async def _cancel_all(self, path, params, received_at_ms):
        return 200, {'result': []}

    async def _get_markets(self, path: str, params: Dict[str, Any], received_at_ms: int):
        return await self._execute_api_call('get_markets')

    async def _get_depth(self, path: str, params: Dict[str, Any], received_at_ms: int):
        symbol = params.get('symbol')
        if not symbol:
            return self._bad_request('Missing "symbol" query parameter')
        depth_param = params.get('depth')
        depth = int(depth_param) if depth_param is not None else None
        return await self._execute_api_call('get_depth', symbol, depth)

    async def _get_account(self, path: str, params: Dict[str, Any], received_at_ms: int):
        return await self._execute_api_call('get_account')

    async def _create_order(self, path: str, params: Dict[str, Any], received_at_ms: int):
        if not params:
            return self._bad_request('Order payload is required')
        return await self._execute_api_call('create_order', params)

    async def _update_order(self, path: str, params: Dict[str, Any], received_at_ms: int):
        if not params:
            return self._bad_request('Update payload is required')
        return await self._execute_api_call('update_order', params)

    async def _cancel_order(self, path: str, params: Dict[str, Any], received_at_ms: int):
        if not params:
            return self._bad_request('Query parameters are required to cancel an order')
        return await self._execute_api_call('cancel_order', params)

    async def _get_order(self, path: str, params: Dict[str, Any], received_at_ms: int):
        if not params:
            return self._bad_request('Order query parameters are required')
        return await self._execute_api_call('get_order', params)

    async def _get_orders(self, path: str, params: Dict[str, Any], received_at_ms: int):
        return await self._execute_api_call('get_orders', params)

    async def _withdraw(self, path: str, params: Dict[str, Any], received_at_ms: int):
        required_keys = {'destination', 'asset', 'amount', 'gasAsset', 'gasAmount'}
        missing = required_keys - params.keys()
        if missing:
            return self._bad_request(f'Missing required withdraw fields: {", ".join(sorted(missing))}')
        return await self._execute_api_call('withdraw', params)

    async def _get_withdraw(self, path: str, params: Dict[str, Any], received_at_ms: int):
        withdraw_id = params.get('withdrawId') or params.get('withdraw_id')
        if not withdraw_id:
            return self._bad_request('withdrawId query parameter is required')
        return await self._execute_api_call('get_withdraw', str(withdraw_id))

    async def _get_inbound_addresses(self, path: str, params: Dict[str, Any], received_at_ms: int):
        return await self._execute_api_call('get_inbound_addresses')

    async def _get_outbound_fees(self, path: str, params: Dict[str, Any], received_at_ms: int):
        return await self._execute_api_call('get_outbound_fees')

    async def _get_tx_details(self, path: str, params: Dict[str, Any], received_at_ms: int):
        tx_id = params.get('txId') or params.get('tx_id')
        if not tx_id:
            return self._bad_request('txId query parameter is required')
        return await self._execute_api_call('get_tx_details', str(tx_id))

    async def _get_deposit_instructions(self, path: str, params: Dict[str, Any], received_at_ms: int):
        inbound_result = await self._execute_api_call('get_inbound_addresses')
        status, data = inbound_result
        if status != 200:
            return inbound_result
        instructions = {
            'inbound': data,
            'fromAddresses': {k: v for k, v in self._from_addresses.items() if v},
        }
        if self._websocket_url:
            instructions['websocketUrl'] = self._websocket_url
        return 200, instructions

    async def _execute_api_call(self, method: str, *args, success_status: int = 200):
        api = self._api
        if api is None:
            return self._api_not_ready()
        func = getattr(api, method)
        try:
            result = await func(*args)
            return success_status, result
        except HarborAPIError as exc:
            self._logger.error('Harbor API error (%s): %s', exc.status, exc)
            return exc.status, exc.to_response()
        except Exception as exc:  # pragma: no cover - defensive logging
            self._logger.exception('Unexpected Harbor integration error: %r', exc)
            return 500, {'error': {'message': str(exc)}}

    @staticmethod
    def _bad_request(message: str):
        return 400, {'error': {'message': message}}

    @staticmethod
    def _api_not_ready():
        return 503, {'error': {'message': 'Harbor API client not initialised'}}
