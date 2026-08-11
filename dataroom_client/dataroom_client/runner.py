"""A shared background event loop for driving the async client from sync code."""

import asyncio
import atexit
import logging
import threading
from typing import Any

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

        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)
        return future.result()

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
