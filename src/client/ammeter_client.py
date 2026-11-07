"""
Unified, defensive client for all ammeter emulators.

Protocol (verified against Ammeters/base_ammeter.py): one TCP connection per
measurement; the server sends the float once with sendall() and then closes
the connection. The reply is therefore EOF-framed: the client reads until the
server closes the connection (or a size bound is hit), because a single
recv() call is never guaranteed to return the whole payload.
"""
import socket
import time
from dataclasses import dataclass, field
from typing import Optional

from src.testing.sampler import ConfigError


class AmmeterError(Exception):
    """A measurement attempt failed (connection, timeout, or bad response)."""


ERROR_SIMULATION_MODES = ("wrong_command", "connection_refused", "drop_response")


@dataclass
class ClientConfig:
    connect_timeout_seconds: float = 2.0
    read_timeout_seconds: float = 2.0
    retries: int = 2
    retry_backoff_seconds: float = 0.2
    max_response_bytes: int = 4096  # bound for the EOF-framed read
    # Bonus: client-side error simulation (config key testing.error_simulation)
    error_simulation: dict = field(default_factory=dict)

    def __post_init__(self):
        """Fail fast on a bad client config (e.g. a null or negative value in the YAML)."""
        def number(value, name, minimum, allow_equal):
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or value != value or value in (float("inf"), float("-inf")):
                raise ConfigError(f"client.{name} must be a number, got {value!r}")
            if value < minimum or (value == minimum and not allow_equal):
                raise ConfigError(f"client.{name} is out of range, got {value!r}")
        number(self.connect_timeout_seconds, "connect_timeout_seconds", 0, False)
        number(self.read_timeout_seconds, "read_timeout_seconds", 0, False)
        number(self.retry_backoff_seconds, "retry_backoff_seconds", 0, True)
        if isinstance(self.retries, bool) or not isinstance(self.retries, int) or self.retries < 0:
            raise ConfigError(f"client.retries must be an integer >= 0, got {self.retries!r}")
        if isinstance(self.max_response_bytes, bool) or not isinstance(self.max_response_bytes, int) \
                or self.max_response_bytes <= 0:
            raise ConfigError(
                f"client.max_response_bytes must be a positive integer, got {self.max_response_bytes!r}")
        sim = self.error_simulation or {}
        if not isinstance(sim, dict):
            raise ConfigError("error_simulation must be a mapping")
        if sim.get("enabled"):
            if sim.get("mode", "wrong_command") not in ERROR_SIMULATION_MODES:
                raise ConfigError(
                    f"error_simulation.mode must be one of {ERROR_SIMULATION_MODES}, "
                    f"got {sim.get('mode')!r}")
            number(sim.get("probability", 0.0), "error_simulation.probability", 0, True)
            if sim.get("probability", 0.0) > 1:
                raise ConfigError("error_simulation.probability must be between 0 and 1")


class AmmeterClient:
    def __init__(self, name: str, port: int, command: str, config: Optional[ClientConfig] = None):
        self.name = name
        self.port = port
        self.command = command.encode("utf-8") if isinstance(command, str) else command
        self.config = config or ClientConfig()

    def measure_once(self) -> float:
        """Single measurement with retries. Raises AmmeterError after the last failure."""
        last_error: Optional[Exception] = None
        attempts = 1 + self.config.retries
        for attempt in range(1, attempts + 1):
            try:
                return self._attempt()
            except AmmeterError as exc:
                last_error = exc
                if attempt < attempts:
                    time.sleep(self.config.retry_backoff_seconds)
        raise AmmeterError(
            f"{self.name}: measurement failed after {attempts} attempts: {last_error}"
        )

    def _attempt(self) -> float:
        port, command = self._maybe_simulate_error()
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.config.connect_timeout_seconds)
                sock.connect(("localhost", port))
                sock.settimeout(self.config.read_timeout_seconds)
                if command is not None:
                    sock.sendall(command)
                data = self._read_until_eof(sock)
        except socket.timeout as exc:
            raise AmmeterError(f"timeout talking to {self.name} on port {port}") from exc
        except OSError as exc:
            raise AmmeterError(f"connection to {self.name} on port {port} failed: {exc}") from exc

        if not data:
            # The server closes the connection without replying when the
            # command does not match its expected bytes exactly.
            raise AmmeterError(
                f"{self.name} on port {port} returned no data "
                f"(command rejected by the device?)"
            )
        try:
            return float(data.decode("utf-8").strip())
        except ValueError as exc:
            raise AmmeterError(
                f"{self.name} on port {port} returned a non-numeric response: {data!r}"
            ) from exc

    def _read_until_eof(self, sock) -> bytes:
        """Read until the server closes the connection, bounded by max_response_bytes."""
        chunks = []
        total = 0
        while True:
            chunk = sock.recv(1024)
            if not chunk:  # server closed: end of this reply
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > self.config.max_response_bytes:
                raise AmmeterError(
                    f"{self.name} on port {self.port} sent more than "
                    f"{self.config.max_response_bytes} bytes - not a measurement reply"
                )
        return b"".join(chunks)

    def _maybe_simulate_error(self):
        """
        Bonus hook (config key testing.error_simulation): with the configured
        probability, corrupt this attempt. Faults are injected client-side
        only; the supplied emulators are never touched. Probability is per
        attempt - with retries, a sample fails only if every attempt fails.
        """
        sim = self.config.error_simulation or {}
        if not sim.get("enabled"):
            return self.port, self.command
        import random
        if random.random() >= float(sim.get("probability", 0.0)):
            return self.port, self.command
        mode = sim.get("mode", "wrong_command")
        if mode == "wrong_command":
            return self.port, b"SIMULATED_WRONG_COMMAND"
        if mode == "connection_refused":
            return self.port + 1000, self.command  # nothing listens there
        if mode == "drop_response":
            return self.port, None  # connect but send nothing -> read timeout
        return self.port, self.command
