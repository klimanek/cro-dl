import time


class Timer:
    """
    Context Manager measuring time needed to run and finish a piece of code.

    Example:

        with Timer() as timer:
            my_code_goes_here

    Useful when finding a bottleneck in codes.
    """

    def __init__(self):
        self.start_time = 0

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *_):
        elapsed_time = time.time() - self.start_time
        print(f"Time elapsed: {elapsed_time} seconds")
