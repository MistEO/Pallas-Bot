from concurrent.futures import thread
import random
import threading

ROULETTE_VALUES = (1, 2, 3, 4, 5, 6)
ROULETTE_WEIGHTS = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
ROULETTE_DELTA = 0.01
ROULETTE_MINIMUM_WEIGHT = 0.9
ROULETTE_LOCK = threading.RLock()


def roulette_random() -> int:
    '''Returns a value between [1,6]. Reduces the probability a bit when a number is generated.'''
    ROULETTE_LOCK.acquire()
    try:
        result = random.choices(ROULETTE_VALUES, weights=ROULETTE_WEIGHTS)[0]
        index = result - 1 # index of the weight
        if ROULETTE_WEIGHTS[index] > ROULETTE_MINIMUM_WEIGHT:
            for i in range(len(ROULETTE_WEIGHTS)):
                if i == index:
                    ROULETTE_WEIGHTS[i] -= 5*ROULETTE_DELTA
                else:
                    ROULETTE_WEIGHTS[i] += ROULETTE_DELTA
        return result
    finally:
        ROULETTE_LOCK.release()
