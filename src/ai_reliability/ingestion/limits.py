"""Bound request bodies before parsing to prevent unbounded resource consumption."""
from starlette.responses import JSONResponse

ROUTE_LIMITS = {
    "/analyze": 2 * 1024 * 1024,
    "/documents/paste": 2 * 1024 * 1024,
    "/form-experiments": 2 * 1024 * 1024,
    "/documents/extract": 5 * 1024 * 1024,
}
DEFAULT_POST_LIMIT = 10 * 1024 * 1024  # 10 MiB


class RequestBodyLimit:
    """ASGI Middleware bounding request body sizes across all incoming requests."""

    def __init__(self, app, default_limit: int = DEFAULT_POST_LIMIT, route_limits: dict[str, int] | None = None):
        self.app = app
        self.default_limit = default_limit
        self.route_limits = route_limits if route_limits is not None else ROUTE_LIMITS

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)

        path = scope.get("path", "")
        limit = self.route_limits.get(path, self.default_limit)

        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                limit_mib = limit // (1024 * 1024)
                return await JSONResponse(
                    {"detail": f"Request body exceeds the {limit_mib} MiB limit."},
                    status_code=413,
                )(scope, receive, send)
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


# Backward compatibility alias
FormBodyLimit = RequestBodyLimit
