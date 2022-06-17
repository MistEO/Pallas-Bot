import unittest
from plugins.roulette.pseudorandom import RouletteRandomizer

GROUP = 1
OTHER_GROUP = 2


class TestRouletteRandomizer(unittest.TestCase):
    def test_roulette_random(self):
        '''Test roulette_random().'''
        roulette = RouletteRandomizer()

        # test probability changes
        original_weights = roulette.ROULETTE_WEIGHTS[GROUP][:]
        result = roulette.roulette_random(GROUP)
        index = result - 1
        for i in range(len(original_weights)):
            actual_weight = roulette.ROULETTE_WEIGHTS[GROUP][i]
            if i == index:
                expected_weight = 0.05
            else:
                expected_weight = 0.19
            self.assertAlmostEqual(expected_weight, actual_weight)

        # test group isolation
        original_weights = roulette.ROULETTE_WEIGHTS[GROUP][:]
        original_weights_other = roulette.ROULETTE_WEIGHTS[OTHER_GROUP][:]
        result = roulette.roulette_random(OTHER_GROUP)
        index = result - 1
        for i in range(len(original_weights_other)):
            actual_weight = roulette.ROULETTE_WEIGHTS[OTHER_GROUP][i]
            print(i, index)
            if i == index:
                expected_weight = 0.05
            else:
                expected_weight = 0.19
            self.assertAlmostEqual(expected_weight, actual_weight)
        for i in range(len(original_weights)):
            actual_weight = roulette.ROULETTE_WEIGHTS[GROUP][i]
            expected_weight = original_weights[i]
            self.assertAlmostEqual(expected_weight, actual_weight)
