from collections import defaultdict
import random


class RouletteRandomizer:
    def __init__(self):
        self.ROULETTE_VALUES = (1, 2, 3, 4, 5, 6)
        self.ROULETTE_WEIGHTS: defaultdict[int, list[float]] = defaultdict(
            lambda: [1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        self.ROULETTE_DELTA = 0.01
        self.ROULETTE_MINIMUM_WEIGHT = 0.9

        self.ROULETTE_MISS_PROB_BASE = 0.125
        self.ROULETTE_MISS_PROB: defaultdict[int, float] = defaultdict(
            lambda: self.ROULETTE_MISS_PROB_BASE)
        self.ROULETTE_MISS_DELTA = 0.001

    def roulette_random(self, group: int) -> int:
        '''Returns a value between [1,6]. Reduces the probability a bit when a number is generated.'''
        result = random.choices(
            self.ROULETTE_VALUES, weights=self.ROULETTE_WEIGHTS[group])[0]
        index = result - 1  # index of the weight
        if self.ROULETTE_WEIGHTS[group][index] > self.ROULETTE_MINIMUM_WEIGHT:
            for i in range(len(self.ROULETTE_WEIGHTS[group])):
                if i == index:
                    self.ROULETTE_WEIGHTS[group][i] -= 5*self.ROULETTE_DELTA
                else:
                    self.ROULETTE_WEIGHTS[group][i] += self.ROULETTE_DELTA
        return result

    def roulette_miss_random(self, group: int) -> bool:
        '''Returns whether the shot missed or not. The probability will increase a bit if it is not missed.'''
        is_failed = random.random() < self.ROULETTE_MISS_PROB[group]
        if not is_failed:
            self.ROULETTE_MISS_PROB[group] += self.ROULETTE_MISS_DELTA
        else:
            self.ROULETTE_MISS_PROB[group] = self.ROULETTE_MISS_PROB_BASE
        return is_failed


roulette_randomizer = RouletteRandomizer()
