from litestar import get
from litestar.datastructures import ResponseHeader, State


@get(
    "/servers/status",
    response_headers=[ResponseHeader(name="Cache-Control", value="no-store")],
)
async def server_status(state: State) -> dict:
    return await state.server_status.snapshot()
