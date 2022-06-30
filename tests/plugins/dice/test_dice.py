import unittest
from plugins.dice.dice import parse_dice_message, calc_dice, MAX_NUMBER_OF_DICE, MAX_NUMBER_OF_FACES
from typing import List, Tuple


class TestDice(unittest.TestCase):
    def test_parse_dice_message(self):
        '''Test parse_dice_message().'''
        test_cases: List[Tuple[str, bool, int, int]] = [
            # msg, expected_ok, expected_a, expected_x
            ('1d2', True, 1, 2),
            ('0d0', False, 0, 0),
            ('-1d-1', False, 0, 0),
            ('0d-1', False, 0, 0),
            ('-1d0', False, 0, 0),
            (f'{MAX_NUMBER_OF_DICE+1}d{MAX_NUMBER_OF_FACES+1}', False, 0, 0),
            (f'{MAX_NUMBER_OF_DICE+1}d{MAX_NUMBER_OF_FACES}', False, 0, 0),
            (f'{MAX_NUMBER_OF_DICE}d{MAX_NUMBER_OF_FACES+1}', False, 0, 0),
            (f'{MAX_NUMBER_OF_DICE}d{MAX_NUMBER_OF_FACES}',
             True, MAX_NUMBER_OF_DICE, MAX_NUMBER_OF_FACES),
        ]
        for test_case in test_cases:
            with self.subTest(test_case=test_case):
                msg, expected_ok, expected_a, expected_x = test_case
                actual_ok, actual_a, actual_x = parse_dice_message(msg)
                self.assertEqual(expected_ok, actual_ok)
                if actual_ok:
                    self.assertEqual(expected_a, actual_a)
                    self.assertEqual(expected_x, actual_x)

    def test_calc_dice(self):
        '''Test calc_dice().'''
        test_cases: List[Tuple[int, int]] = [
            # since the function to be tested involves random numbers,
            # we will check if the value is within some range.
            # a <= result <= a*x
            # a, x
            (1, 1),
            (10, 1),
            (1, 2),
            (4, 100),
            (100, 100),
        ]
        for test_case in test_cases:
            a, x = test_case
            actual_result = calc_dice(a, x)
            self.assertTrue(a <= actual_result and actual_result <= a*x)


if __name__ == '__main__':
    unittest.main()
