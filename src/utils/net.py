"""Readiness check for the emulators: wait until a TCP port accepts connections."""
import socket
import time


def wait_for_port(port: int, host: str = "localhost", timeout: float = 5.0,
                  interval: float = 0.05) -> None:
    """Return as soon as host:port accepts a connection; raise TimeoutError after `timeout` seconds."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            with socket.create_connection((host, port), timeout=interval):
                return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"nothing is listening on {host}:{port} after {timeout}s")
            time.sleep(interval)
