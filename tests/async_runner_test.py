import asyncio
import time
import pytest
import threading
from unittest.mock import patch
from dataroom_client.dataroom_client.client import AsyncRunner

@pytest.fixture(autouse=True)
def cleanup_async_runner():
    # This fixture ensures that AsyncRunner is reset after each test,
    # preventing state leakage between tests.
    yield
    AsyncRunner.shutdown()

async def sample_coro(delay, result):
    """A simple coroutine for testing."""
    await asyncio.sleep(delay)
    return result

def test_async_runner_run():
    """Test that AsyncRunner can run a simple coroutine and return the result."""
    result = AsyncRunner.run(sample_coro(0.01, "success"))
    assert result == "success"

def test_async_runner_reuses_thread_and_loop():
    """Test that subsequent calls to run() reuse the same event loop and thread."""
    # Run a coroutine to initialize the runner
    initial_thread = AsyncRunner.run(asyncio.to_thread(lambda: threading.current_thread()))
    initial_loop = AsyncRunner._loop
    initial_thread_id = initial_thread.ident

    # Run another coroutine
    next_thread = AsyncRunner.run(asyncio.to_thread(lambda: threading.current_thread()))
    next_loop = AsyncRunner._loop
    next_thread_id = next_thread.ident
    
    assert initial_thread_id == next_thread_id
    assert initial_loop is next_loop

def test_async_runner_shutdown():
    """Test that the shutdown method correctly stops the loop and thread."""
    # Initialize the runner
    AsyncRunner.run(sample_coro(0, "init"))
    assert AsyncRunner._loop.is_running()
    assert AsyncRunner._thread.is_alive()
    
    AsyncRunner.shutdown()
    
    assert AsyncRunner._loop is None
    assert AsyncRunner._thread is None

@patch('atexit.register')
def test_atexit_registration(mock_register):
    """Test that atexit.register is called exactly once during initialization."""
    # The runner initializes on the first call to run()
    AsyncRunner.run(sample_coro(0, "first call"))
    mock_register.assert_called_once_with(AsyncRunner.shutdown)

    # Subsequent calls should not re-register
    AsyncRunner.run(sample_coro(0, "second call"))
    mock_register.assert_called_once() 