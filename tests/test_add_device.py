"""
Extension check: a NEW ammeter is added with a config entry only (plus its
emulator class) and runs through the whole framework unchanged.
"""
import logging
import os
import tempfile
import threading
import unittest

from Ammeters.base_ammeter import AmmeterEmulatorBase
from src.testing.test_framework import AmmeterTestFramework
from src.utils.net import wait_for_port

PORT = 6010


class FlukeAmmeter(AmmeterEmulatorBase):
    @property
    def get_current_command(self) -> bytes:
        return b"MEASURE_FLUKE -get"

    def measure_current(self) -> float:
        return 2.5


CONFIG = """
testing:
  sampling: {measurements_count: 5, sampling_frequency_hz: 20}
ammeters:
  fluke: {port: %d, command: "MEASURE_FLUKE -get"}
analysis:
  accuracy_assessment: {enabled: true}
  visualization: {enabled: false}
result_management: {results_dir: runs, plots_dir: plots}
""" % PORT


class TestAddDevice(unittest.TestCase):
    def test_new_device_runs_with_config_only(self):
        threading.Thread(target=FlukeAmmeter(PORT).start_server, daemon=True).start()
        wait_for_port(PORT)
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with open("config.yaml", "w") as f:
                    f.write(CONFIG)
                report = AmmeterTestFramework("config.yaml").run_test("fluke")
            finally:
                # release the log file so the temp dir can be removed (Windows)
                logger = logging.getLogger("test_run_fluke")
                for h in list(logger.handlers):
                    logger.removeHandler(h)
                    h.close()
                os.chdir(old_cwd)
        self.assertEqual(report["statistics"]["count"], 5)
        self.assertEqual(report["statistics"]["mean"], 2.5)
        self.assertEqual(report["accuracy_assessment"]["status"], "no_documented_model")


if __name__ == "__main__":
    unittest.main()
