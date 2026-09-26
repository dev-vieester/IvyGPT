import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


logger = logging.getLogger("ivy_gpt.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        start_time = time.perf_counter()
        client_host = request.client.host if request.client else "unknown"

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "request_failed request_id=%s method=%s path=%s client=%s duration_ms=%.2f",
                request_id,
                request.method,
                request.url.path,
                client_host,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"

        logger.info(
            "request_completed request_id=%s method=%s path=%s status_code=%s client=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            client_host,
            duration_ms,
        )

        return response
