# startup/patches.py
# Monkey-patches for discord.py.
# This module is imported for side-effects — patches are applied on import.
# Must be imported AFTER loading .env, but BEFORE any project imports.
import asyncio
import discord


# --- Patch 1: _schedule_event ---
# Issue: after Client.close() discord.py sets self.loop = MISSING, but
# WebSocket events (on_close, on_disconnect) might still arrive and try
# to call self.loop.create_task(). The patch catches MISSING and uses
# active running asyncio loop.

def _patched_schedule_event(self, coro, event_name, *args, **kwargs):
    from discord.utils import MISSING as _MISSING
    wrapped = self._run_event(coro, event_name, *args, **kwargs)
    loop = getattr(self, 'loop', _MISSING)
    if loop is _MISSING:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
    try:
        return loop.create_task(wrapped, name=f'discord.py: {event_name}')
    except Exception:
        return None

discord.client.Client._schedule_event = _patched_schedule_event


# --- Patch 2: connect() ---
# Issue: during initial failed connection attempt self.ws remains None,
# but ReconnectWebSocket / OSError / backoff handlers access
# self.ws.sequence, self.ws.gateway, self.ws.session_id causing:
#   'NoneType' object has no attribute 'sequence'
# The patch replaces self.ws accesses with safe fallback when self.ws is None.

async def _patched_connect(self, *, reconnect: bool = True) -> None:
    from discord.backoff import ExponentialBackoff
    from discord.gateway import DiscordWebSocket, ReconnectWebSocket
    from discord.errors import (
        GatewayNotFound, ConnectionClosed, HTTPException, PrivilegedIntentsRequired
    )
    import aiohttp as _aiohttp

    def _ws_attr(attr, default=None):
        ws = getattr(self, 'ws', None)
        if ws is None:
            return default
        return getattr(ws, attr, default)

    backoff = ExponentialBackoff()
    ws_params = {
        'initial': True,
        'shard_id': self.shard_id,
    }
    while not self.is_closed():
        try:
            coro = DiscordWebSocket.from_client(self, **ws_params)
            self.ws = await asyncio.wait_for(coro, timeout=60.0)
            ws_params['initial'] = False
            while True:
                await self.ws.poll_event()
        except ReconnectWebSocket as e:
            import logging as _logging
            _logging.getLogger('discord.client').debug('Got a request to %s the websocket.', e.op)
            self.dispatch('disconnect')
            ws_params.update(
                sequence=_ws_attr('sequence'),
                resume=e.resume,
                session=_ws_attr('session_id'),
            )
            if e.resume:
                gw = _ws_attr('gateway')
                if gw is not None:
                    ws_params['gateway'] = gw
            continue
        except (
            OSError,
            HTTPException,
            GatewayNotFound,
            ConnectionClosed,
            _aiohttp.ClientError,
            asyncio.TimeoutError,
        ) as exc:
            self.dispatch('disconnect')
            if not reconnect:
                await self.close()
                if isinstance(exc, ConnectionClosed) and exc.code == 1000:
                    return
                raise

            if self.is_closed():
                return

            if isinstance(exc, OSError) and exc.errno in (54, 10054):
                ws_params.update(
                    sequence=_ws_attr('sequence'),
                    gateway=_ws_attr('gateway'),
                    initial=False,
                    resume=True,
                    session=_ws_attr('session_id'),
                )
                continue

            if isinstance(exc, ConnectionClosed):
                if exc.code == 4014:
                    raise PrivilegedIntentsRequired(exc.shard_id) from None
                if exc.code != 1000:
                    await self.close()
                    raise

            retry = backoff.delay()
            import logging as _logging
            _logging.getLogger('discord.client').exception('Attempting a reconnect in %.2fs', retry)
            await asyncio.sleep(retry)
            ws_params.update(
                sequence=_ws_attr('sequence'),
                gateway=_ws_attr('gateway'),
                resume=True,
                session=_ws_attr('session_id'),
            )

discord.client.Client.connect = _patched_connect
