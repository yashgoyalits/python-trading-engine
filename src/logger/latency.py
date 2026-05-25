# src/utils/latency.py
import time
import asyncio
import functools
from src.logger import log

def latency(label: str = None):
    def decorator(fn):
        _label = label or fn.__qualname__

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = await fn(*args, **kwargs)
            log.info(f"[LATENCY] {_label} = {(time.perf_counter() - t0) * 1000:.3f}ms")
            return result

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            result = fn(*args, **kwargs)
            log.info(f"[LATENCY] {_label} = {(time.perf_counter() - t0) * 1000:.3f}ms")
            return result

        return async_wrapper if asyncio.iscoroutinefunction(fn) else sync_wrapper
    return decorator