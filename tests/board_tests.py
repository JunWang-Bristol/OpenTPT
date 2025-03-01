import unittest
import context  # noqa: F401
from board import Board
import random
import time
import os
import json


class BoardsTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.abspath(os.path.join(os.getcwd(), os.path.dirname(__file__), os.pardir, "hardware_configuration.json"))) as f:
            cls.configuration = json.load(f)
            print(cls.configuration)

        cls.but = Board.factory(cls.configuration['board'], cls.configuration["board_port"])
        cls.but.reset()
        print(f"Starting tests for {cls.configuration['board']}")

    @classmethod
    def tearDownClass(cls):
        print(f"\nFinishing tests for {cls.configuration['board']}")
        cls.but.close()

    def test_identification(self):
        self.assertEqual("OPEN_TPT,2402,00000000,0.0.1\r", self.but.get_identification())

    def test_version(self):
        self.assertEqual("1999.0\r", self.but.get_version())

    def test_pulses(self):
        self.but.reset()
        self.but.clear_pulses()
        self.but.add_pulse(0.01)
        self.but.add_pulse(0.002)
        self.but.add_pulse(0.00009)
        self.but.add_pulse(42.49e-7)
        self.but.add_pulse(42.5e-7)
        pulses = self.but.read_pulses()
        self.assertEqual([0.01, 0.002, 9e-05, 4e-6, 4.5e-6], pulses)

    def test_minimum_period(self):
        self.but.reset()
        self.assertEqual(5e-7, self.but.get_minimum_period())

    def test_train_pulses_count(self):
        self.but.reset()
        self.assertEqual(0, self.but.count_trains())

    def test_run_train(self):
        self.but.reset()
        self.but.clear_pulses()
        self.but.add_pulse(0.000005)
        self.but.add_pulse(0.000002)
        # self.but.add_pulse(0.003)
        # self.but.add_pulse(0.0007)
        self.but.run_pulses(3)
        time.sleep(0.1)
        self.assertEqual(3, self.but.count_trains())
        self.but.run_pulses(4)
        time.sleep(0.1)
        self.assertEqual(7, self.but.count_trains())


if __name__ == '__main__':  # pragma: no cover
    unittest.main()
