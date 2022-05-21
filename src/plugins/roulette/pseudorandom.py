from concurrent.futures import thread
import random
import threading


class RouletteRandomizer:
    def __init__(self):
        self.ROULETTE_VALUES = (1, 2, 3, 4, 5, 6)
        self.ROULETTE_WEIGHTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        self.ROULETTE_DELTA = 0.01
        self.ROULETTE_MINIMUM_WEIGHT = 0.9
        self.ROULETTE_LOCK = threading.RLock()

        self.ROULETTE_MISS_PROB_BASE = 0.125
        self.ROULETTE_MISS_PROB = self.ROULETTE_MISS_PROB_BASE
        self.ROULETTE_MISS_DELTA = 0.001
        self.ROULETTE_MISS_LOCK = threading.RLock()

    def roulette_random(self) -> int:
        '''Returns a value between [1,6]. Reduces the probability a bit when a number is generated.'''
        self.ROULETTE_LOCK.acquire()
        try:
            result = random.choices(
                self.ROULETTE_VALUES, weights=self.ROULETTE_WEIGHTS)[0]
            index = result - 1  # index of the weight
            if self.ROULETTE_WEIGHTS[index] > self.ROULETTE_MINIMUM_WEIGHT:
                for i in range(len(self.ROULETTE_WEIGHTS)):
                    if i == index:
                        self.ROULETTE_WEIGHTS[i] -= 5*self.ROULETTE_DELTA
                    else:
                        self.ROULETTE_WEIGHTS[i] += self.ROULETTE_DELTA
            return result
        finally:
            self.ROULETTE_LOCK.release()

    def roulette_miss_random(self) -> bool:
        '''Returns whether the shot missed or not. The probability will increase a bit if it is not missed.'''
        self.ROULETTE_MISS_LOCK.acquire()
        try:
            is_failed = random.random() < self.ROULETTE_MISS_PROB
            if not is_failed:
                self.ROULETTE_MISS_PROB += self.ROULETTE_MISS_DELTA
            else:
                self.ROULETTE_MISS_PROB = self.ROULETTE_MISS_PROB_BASE
            return is_failed
        finally:
            self.ROULETTE_MISS_LOCK.release()


roulette_randomizer = RouletteRandomizer()
