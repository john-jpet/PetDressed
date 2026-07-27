from __future__ import annotations

import json
import logging
import time
import uuid
from collections import Counter

from fastapi import FastAPI, Request, Response

logger = logging.getLogger("petdressed.requests")
request_counts: Counter[tuple[str, str, int]] = Counter()
request_duration_ms: Counter[tuple[str, str]] = Counter()


def configure_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_metrics(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = round((time.perf_counter() - started) * 1000)
            logger.exception(
                json.dumps(
                    {
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                        "status": 500,
                        "latency_ms": elapsed,
                    }
                )
            )
            raise
        elapsed = round((time.perf_counter() - started) * 1000)
        request_counts[request.method, request.url.path, response.status_code] += 1
        request_duration_ms[request.method, request.url.path] += elapsed
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["referrer-policy"] = "same-origin"
        response.headers["permissions-policy"] = "camera=(self), geolocation=(self)"
        logger.info(
            json.dumps(
                {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "latency_ms": elapsed,
                }
            )
        )
        return response

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        lines = []
        for (method, path, status), count in sorted(request_counts.items()):
            labels = f'method="{method}",path="{path}",status="{status}"'
            lines.append(f"petdressed_http_requests_total{{{labels}}} {count}")
        for (method, path), duration in sorted(request_duration_ms.items()):
            labels = f'method="{method}",path="{path}"'
            lines.append(f"petdressed_http_request_duration_ms_sum{{{labels}}} {duration}")
        return Response("\n".join(lines) + "\n", media_type="text/plain")
