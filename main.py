import sys
import threading
import time

from Ammeters.Circutor_Ammeter import CircutorAmmeter
from Ammeters.Entes_Ammeter import EntesAmmeter
from Ammeters.Greenlee_Ammeter import GreenleeAmmeter
from Ammeters.client import request_current_from_ammeter
from src.utils.net import wait_for_port

EMULATOR_PORTS = (5001, 5002, 5003)


def run_greenlee_emulator():
    greenlee = GreenleeAmmeter(5001)
    greenlee.start_server()

def run_entes_emulator():
    entes = EntesAmmeter(5002)
    entes.start_server()

def run_circutor_emulator():
    circutor = CircutorAmmeter(5003)
    circutor.start_server()

def start_emulators():
    """Start each ammeter emulator in a separate daemon thread."""
    threading.Thread(target=run_greenlee_emulator, daemon=True).start()
    threading.Thread(target=run_entes_emulator, daemon=True).start()
    threading.Thread(target=run_circutor_emulator, daemon=True).start()

def demo_requests():
    """Request one measurement from each ammeter."""
    # Fix #1: send the full command; the emulators ignore a prefix (see DESIGN_DECISIONS.md).
    request_current_from_ammeter(5001, b'MEASURE_GREENLEE -get_measurement')
    request_current_from_ammeter(5002, b'MEASURE_ENTES -get_data')
    request_current_from_ammeter(5003, b'MEASURE_CIRCUTOR -get_measurement -current')

if __name__ == "__main__":
    start_emulators()

    # Wait until each emulator accepts connections instead of sleeping a fixed time.
    for port in EMULATOR_PORTS:
        wait_for_port(port)

    demo_requests()

    # "--serve": keep the emulators running so an external test framework
    # (e.g. examples/run_tests.py) can connect to them.
    if "--serve" in sys.argv:
        print("Emulators are running on ports 5001/5002/5003. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
