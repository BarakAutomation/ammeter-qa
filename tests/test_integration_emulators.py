"""
Integration: the real supplied emulator classes, on dedicated test ports
(6001-6003, so they never clash with a running main.py --serve).
"""
import threading
import unittest

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from src.client.ammeter_client import AmmeterClient, AmmeterError, ClientConfig
from src.utils.net import wait_for_port

EMULATORS = [
    ("greenlee", GreenleeAmmeter, 6001),
    ("entes", EntesAmmeter, 6002),
    ("circutor", CircutorAmmeter, 6003),
]


class TestRealEmulators(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for _, cls_, port in EMULATORS:
            threading.Thread(target=cls_(port).start_server, daemon=True).start()
        for _, _, port in EMULATORS:
            wait_for_port(port)

    def test_each_emulator_answers_its_exact_command(self):
        for name, cls_, port in EMULATORS:
            instance = cls_(port)
            client = AmmeterClient(name, port, instance.get_current_command,
                                   ClientConfig(read_timeout_seconds=2.0))
            value = client.measure_once()
            self.assertIsInstance(value, float, name)

    def test_wrong_command_gets_no_data(self):
        for name, _, port in EMULATORS:
            client = AmmeterClient(name, port, b"DEFINITELY_WRONG",
                                   ClientConfig(read_timeout_seconds=2.0))
            with self.assertRaisesRegex(AmmeterError, "no data", msg=name):
                client.measure_once()


if __name__ == "__main__":
    unittest.main()
