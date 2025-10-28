from typing import Awaitable, Callable

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import web

from harbor.dex_proxy.harbor_api import HarborAPI, HarborAPIError


async def _start_test_server(routes: list[tuple[str, str, Callable[[web.Request], Awaitable[web.StreamResponse]]]]):
    app = web.Application()
    for method, path, handler in routes:
        app.router.add_route(method, path, handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    base_url = f'http://127.0.0.1:{port}'
    return runner, site, base_url


@pytest.mark.asyncio
async def test_get_markets_adds_api_key_header():
    seen_headers = {}

    async def handle_markets(request: web.Request):
        seen_headers.update(request.headers)
        return web.json_response({'markets': []})

    runner, site, base_url = await _start_test_server([
        ('GET', '/api/v1/markets', handle_markets),
    ])

    async with aiohttp.ClientSession() as session:
        api = HarborAPI(
            session,
            rest_base=base_url,
            rest_api_path='/api/v1',
            api_key='secret-key',
            request_timeout=5,
            xnode_base=base_url,
            xnode_api_path='/xnode',
        )
        data = await api.get_markets()
        assert data == {'markets': []}

    await runner.cleanup()
    assert seen_headers.get('X-API-KEY') == 'secret-key'


@pytest.mark.asyncio
async def test_close_closes_session():
    session = aiohttp.ClientSession()
    api = HarborAPI(session, rest_base='http://127.0.0.1')

    await api.close()

    assert session.closed


@pytest.mark.asyncio
async def test_error_response_raises_harbor_api_error():
    async def handle_account(request: web.Request):
        return web.json_response({'message': 'boom'}, status=500)

    runner, site, base_url = await _start_test_server([
        ('GET', '/api/v1/account', handle_account),
    ])

    async with aiohttp.ClientSession() as session:
        api = HarborAPI(
            session,
            rest_base=base_url,
            rest_api_path='/api/v1',
            api_key='key',
            request_timeout=5,
            xnode_base=base_url,
            xnode_api_path='/xnode',
        )
        with pytest.raises(HarborAPIError) as exc_info:
            await api.get_account()

    await runner.cleanup()
    assert exc_info.value.status == 500
    assert exc_info.value.payload == {'message': 'boom'}


@pytest.mark.asyncio
async def test_xnode_request_uses_secondary_base():
    async def handle_inbound(request: web.Request):
        return web.json_response({'addresses': []})

    runner, site, base_url = await _start_test_server([
        ('GET', '/xnode/inbound_addresses', handle_inbound),
    ])

    async with aiohttp.ClientSession() as session:
        api = HarborAPI(
            session,
            rest_base=base_url,
            rest_api_path='/api/v1',
            api_key=None,
            request_timeout=5,
            xnode_base=base_url,
            xnode_api_path='/xnode',
        )
        data = await api.get_inbound_addresses()
        assert data == {'addresses': []}

    await runner.cleanup()
