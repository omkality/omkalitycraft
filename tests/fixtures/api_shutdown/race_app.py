"""Fixture reproducing a shutdown race with a delayed asyncio wakeup."""

import asyncio
import contextlib
import time


async def churn():
    while True:
        await asyncio.sleep(0)
async def app(scope, receive, send):
    if scope['type'] == 'lifespan':
        while True:
            event = await receive()
            if event['type'] == 'lifespan.startup':
                loop = asyncio.get_running_loop()
                wake = loop._write_to_self
                def delayed_wakeup(wake=wake):
                    time.sleep(0.2)
                    wake()
                loop._write_to_self = delayed_wakeup
                task = loop.create_task(churn())
                await send({'type': 'lifespan.startup.complete'})
            elif event['type'] == 'lifespan.shutdown':
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
                await send({'type': 'lifespan.shutdown.complete'})
                return
    elif scope['type'] == 'http':
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'fixture'})
