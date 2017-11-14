
import threading
import time
import unittest

import mtprof


def consume_cpu_simple(delay):
    deadline = time.monotonic() + delay
    while time.monotonic() < deadline:
        pass


class TestInternals(unittest.TestCase):

    def test_default_timer(self):
        DELAY = 1.4
        TOL = 0.2
        f = mtprof._default_timer()

        t1 = f()
        consume_cpu_simple(DELAY)
        dt = f() - t1
        self.assertGreaterEqual(dt, DELAY - TOL)
        self.assertLessEqual(dt, DELAY + TOL)

        t = threading.Thread(target=consume_cpu_simple, args=(DELAY,))
        t1 = f()
        t.start()
        t.join()
        dt = f() - t1

        self.assertLess(dt, 0 + TOL)



if __name__ == "__main__":
    unittest.main()
