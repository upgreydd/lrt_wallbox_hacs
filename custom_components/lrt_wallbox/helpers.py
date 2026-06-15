"""Helper functions for the LRT Wallbox integration."""

import asyncio
import itertools
import logging
from asyncio import PriorityQueue
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from lrt_wallbox.msg_types import TransactionStopResponse
from requests.exceptions import ConnectionError, ReadTimeout

_LOGGER = logging.getLogger(__name__)


def tag_id_to_hex(tag_id: list[int]) -> str:
    """Convert a list of tag ID bytes to a hexadecimal string."""
    return "".join(f"{b:02X}" for b in tag_id)


class WallboxClientExecutor:
    """Serializes access to the (synchronous) WallboxClient.

    The device tolerates only one in-flight request at a time, so every call is
    funnelled through a single asyncio worker that runs the blocking client
    method in the executor thread pool. This class is purely transport — entity
    state lives in the DataUpdateCoordinator.
    """

    def __init__(self, client: Any, hass: HomeAssistant) -> None:
        """Initialize the WallboxClientExecutor."""
        self._client = client
        self._hass = hass
        self._counter = itertools.count()
        self._queue: PriorityQueue[
            tuple[int, int, str, tuple, dict, asyncio.Future]
        ] = PriorityQueue()
        self._task: asyncio.Task | None = None
        self.start()

    def start(self) -> None:
        """Start the background task processing the queue."""
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            priority, seq, method_name, args, kwargs, future = await self._queue.get()

            if future.cancelled():
                continue

            if method_name == "__shutdown__":
                if not future.done():
                    future.set_result(True)
                break

            try:
                method: Callable = getattr(self._client, method_name)
                result = await self._hass.async_add_executor_job(
                    method, *args, **kwargs
                )
            except (ConnectionError, ReadTimeout) as e:
                if method_name == "util_restart":
                    _LOGGER.debug(
                        "Wallbox likely restarted during util_restart (timeout), ignoring."
                    )
                    if not future.done():
                        future.set_result(None)
                else:
                    if not future.done():
                        future.set_exception(e)
            except Exception as e:  # noqa: BLE001 - propagate to the caller's future
                if not future.done() and not future.cancelled():
                    future.set_exception(e)
            else:
                if not future.done() and not future.cancelled():
                    future.set_result(result)

    async def call(
        self, method_name: str, *args, priority: int = 5, timeout: int = 10, **kwargs
    ) -> Any:
        """Call a method on the WallboxClient with priority and timeout."""
        future: asyncio.Future = self._hass.loop.create_future()
        seq = next(self._counter)
        await self._queue.put((priority, seq, method_name, args, kwargs, future))

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except (TimeoutError, asyncio.CancelledError) as e:
            if not future.done() and not future.cancelled():
                future.set_exception(e)
            raise

    async def shutdown(self) -> None:
        """Shutdown the executor gracefully."""
        if self._task:
            future: asyncio.Future = self._hass.loop.create_future()
            seq = next(self._counter)
            await self._queue.put((0, seq, "__shutdown__", (), {}, future))
            try:
                await asyncio.wait_for(future, timeout=5)
            except TimeoutError:
                _LOGGER.warning("Timeout while shutting down WallboxClientExecutor")
            await self._task
            self._task = None


def get_last_5_transactions(
    transaction_log: list[TransactionStopResponse],
) -> list[dict[str, int | Any]]:
    """Get the last 5 transactions from the transaction log."""

    def _norm_ts(ts: str) -> str:
        """Normalize timestamp to ISO format with UTC timezone."""
        return ts.replace(" UTC", "Z")

    def _sort_key(t: TransactionStopResponse) -> str:
        return _norm_ts(t.endTime)

    tx_sorted = sorted(transaction_log, key=_sort_key, reverse=True)

    return [
        {
            "startTime": _norm_ts(t.startTime),
            "endTime": _norm_ts(t.endTime),
            "energy": int(t.energy),
        }
        for t in tx_sorted[:5]
    ]
