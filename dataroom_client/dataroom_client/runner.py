"""A shared background event loop for driving the async client from sync code."""

import asyncio
import atexit
import concurrent.futures
import logging
import sys
import threading
import traceback
from typing import Any

from .models import DataRoomError

logger = logging.getLogger(__name__)


class AsyncRunner:
    """
    Manages a single, shared event loop in a background thread
    to run async functions from a synchronous context using classmethods.

    The shutdown method is automatically registered to be called on exit.
    """
    _loop: asyncio.AbstractEventLoop | None = None
    _thread: threading.Thread | None = None
    _lock = threading.Lock() # To ensure thread-safe initialization
    # Seconds a sync call or the next iterator item may take before it fails.
    call_timeout: float = 600

    @classmethod
    def _initialize(cls) -> None:
        """Initializes the background event loop and thread if not already done."""
        with cls._lock:
            if cls._thread is not None:
                return

            cls._loop = asyncio.new_event_loop()
            cls._thread = threading.Thread(
                target=cls._loop.run_forever,
                daemon=True,
                name="ClassAsyncRunnerThread"
            )
            cls._thread.start()
            # Register the shutdown method to be called when the program exits.
            # This is done here to ensure it's only registered once.
            atexit.register(cls.shutdown)
            logger.debug("Initialized ClassAsyncRunner background thread")

    @classmethod
    def run(cls, coro) -> Any:
        """
        Runs a coroutine on the shared background event loop and returns the result.
        Initializes the loop on the first call.

        @param coro: The coroutine to run.
        @return: The result of the coroutine.
        """
        if cls._thread is None:
            cls._initialize()

        name = getattr(coro, "__qualname__", repr(coro))
        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        try:
            return future.result(timeout=cls.call_timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise DataRoomError(f"{name} did not finish within {cls.call_timeout:.0f}s. {cls.loop_stack()}")

    @classmethod
    def loop_stack(cls) -> str:
        frame = sys._current_frames().get(cls._thread.ident) if cls._thread else None
        if frame is None:
            return "The client's event loop thread is not running."
        return "The client's event loop thread is at:\n" + "".join(traceback.format_stack(frame, limit=6))

    @classmethod
    def submit(cls, coro):
        """
        Schedule a coroutine on the shared background event loop and return the Future.

        Unlike run(), this does not wait for the result; useful for producers feeding queues.
        """
        if cls._thread is None:
            cls._initialize()
        return asyncio.run_coroutine_threadsafe(coro, cls._loop)

    @classmethod
    def shutdown(cls) -> None:
        """
        Cleanly stops the shared event loop.
        This is registered with atexit and called automatically.
        """
        # The check for cls._loop is important because atexit might call this
        # even if the runner was never initialized.
        if cls._loop and cls._loop.is_running():
            logger.debug("Shutting down ClassAsyncRunner background thread...")
            cls._loop.call_soon_threadsafe(cls._loop.stop)
            # It's good practice to have a timeout on join
            cls._thread.join(timeout=5)
            cls._loop.close()
            logger.debug("ClassAsyncRunner has been shut down.")

        cls._loop = None
        cls._thread = None
