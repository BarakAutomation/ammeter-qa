"""Client error handling against one-shot fake TCP servers: timeout, refused connection, retries."""
import socket
import threading
import time
import unittest

from src.client.ammeter_client import AmmeterClient, AmmeterError, ClientConfig


def serve_once(behavior):
    """Start a one-connection server thread; returns its port."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", 0))
    server.listen(1)
    port = server.getsockname()[1]

    def run():
        try:
            conn, _ = server.accept()
            with conn:
                behavior(conn)
        finally:
            server.close()

    threading.Thread(target=run, daemon=True).start()
    return port


def read_request(conn):
    conn.recv(1024)


class TestAmmeterClient(unittest.TestCase):
    def fast(self, **kw):
        kw.setdefault("connect_timeout_seconds", 0.5)
        kw.setdefault("read_timeout_seconds", 0.5)
        kw.setdefault("retries", 0)
        return ClientConfig(**kw)

    def test_read_timeout_when_server_never_answers(self):
        def b(conn):
            read_request(conn)
            time.sleep(2.0)  # longer than the client's read timeout
        port = serve_once(b)
        client = AmmeterClient("t", port, b"CMD", self.fast())
        with self.assertRaisesRegex(AmmeterError, "timeout"):
            client.measure_once()

    def test_connection_refused(self):
        # A port nothing listens on: find one by binding and closing.
        probe = socket.socket()
        probe.bind(("localhost", 0))
        dead_port = probe.getsockname()[1]
        probe.close()
        client = AmmeterClient("t", dead_port, b"CMD", self.fast())
        with self.assertRaisesRegex(AmmeterError, "connection"):
            client.measure_once()

    def test_retry_count(self):
        class CountingClient(AmmeterClient):
            attempts = 0
            def _attempt(self):
                self.attempts += 1
                raise AmmeterError("boom")
        client = CountingClient("t", 1, b"CMD",
                                self.fast(retries=2, retry_backoff_seconds=0.01))
        with self.assertRaisesRegex(AmmeterError, "3 attempts"):
            client.measure_once()
        self.assertEqual(client.attempts, 3)


if __name__ == "__main__":
    unittest.main()
