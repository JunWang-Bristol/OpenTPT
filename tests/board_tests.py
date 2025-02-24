import unittest
import context  # noqa: F401
from board import Board
import random
import time


class NUCLEO_H503RB(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.but = Board.factory("NUCLEO-H503RB", "COM6")
        cls.but.reset()
        print("Starting tests for NUCLEO-H503RB")

    @classmethod
    def tearDownClass(cls):
        print("\nFinishing tests for NUCLEO-H503RB")
        cls.but.close()

    def test_identification(self):
        self.assertEqual("OPEN_TPT,50V3A,00000000,0.0.1\r", self.but.get_identification())

    def test_version(self):
        self.assertEqual("1999.0\r", self.but.get_version())

    def test_pulses(self):
        self.but.clear_pulses()
        self.but.add_pulse(10.01)
        self.but.add_pulse(0.002)
        self.but.add_pulse(0.0000009)
        self.but.add_pulse(42e-12)
        pulses = self.but.read_pulses()
        self.assertEqual([10.01, 0.002, 9e-07, 4.2e-11], pulses)

    def test_minimum_period(self):
        self.assertEqual(1.0 / 250e6, self.but.get_minimum_period())

    def test_train_pulses_count(self):
        self.assertEqual(0, self.but.count_trains())

    def test_run_stop_train(self):
        self.but.run_pulses()
        self.but.stop_pulses()


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
