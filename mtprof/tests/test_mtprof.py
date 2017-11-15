import gc
import io
import pstats
import threading
import time
import unittest

import mtprof


def consume_cpu_simple(delay):
    deadline = time.monotonic() + delay
    while time.monotonic() < deadline:
        pass


def run_until(deadline):
    while time.monotonic() < deadline:
        pass


def consume_cpu(duration, ncalls):
    now = time.monotonic()
    for i in range(ncalls):
        deadline = now + duration * (i + 1) / ncalls
        run_until(deadline)


def f(duration, ncalls):
    consume_cpu(duration, ncalls)

def g(duration, ncalls):
    consume_cpu(duration, ncalls)

def h(duration, ncalls):
    consume_cpu(duration, ncalls)


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


class BaseProfilingTest:

    def get_function_key(self, func):
        try:
            code = func.__code__
        except AttributeError:
            return "", 0, func.__name__
        else:
            return code.co_filename, code.co_firstlineno, code.co_name

    def get_function_repr(self, func):
        try:
            code = func.__code__
        except AttributeError:
            raise
        else:
            # filename:lineno(function)
            return "%s:%d(%s)" % (code.co_filename, code.co_firstlineno, code.co_name)

    def check_function(self, stats, func):
        key = self.get_function_key(func)
        self.assertIn(key, stats, sorted(stats))
        return stats[key]

    def check_in_pstats(self, prof, func, ncalls):
        sio = io.StringIO()
        st = pstats.Stats(prof, stream=sio)
        st.sort_stats('cumtime').print_stats(20)
        sio.seek(0)
        look_for = self.get_function_repr(func)
        for line in sio:
            parts = line.strip().split()
            if parts and parts[-1] == look_for:
                break
        else:
            self.fail("could not find %r in %r" % (look_for, sio.getvalue()))
        nc, tt, percall, ct, cumpercall = parts[:5]
        nc = int(nc.partition('/')[0])
        tt = float(tt)
        ct = float(ct)
        self.assertEqual(nc, ncalls)
        return tt, ct


class TestSingleThread(BaseProfilingTest, unittest.TestCase):
    DURATION = 0.2
    NCALLS = 4

    def profiler(self):
        prof = mtprof.Profile()
        self.addCleanup(prof.close)
        return prof

    def check_stats(self, stats, nruns=1):
        st = self.check_function(stats, f)
        cc, nc, tt, ct, callers = st
        self.assertEqual(nc, nruns)
        self.assertLessEqual(ct, self.DURATION * 1.5)
        self.assertGreaterEqual(ct, self.DURATION * 0.8)

        st = self.check_function(stats, run_until)
        cc, nc, tt, ct, callers = st
        self.assertEqual(nc, self.NCALLS * nruns)
        self.assertLessEqual(ct, self.DURATION * 1.5)

        key = self.get_function_key(consume_cpu)
        self.assertEqual(list(callers), [key])

    def test_enable_disable(self):
        prof = self.profiler()
        prof.enable()
        f(self.DURATION, self.NCALLS)
        prof.disable()
        prof.create_stats()
        self.check_stats(prof.stats)

    def test_enable_disable_twice(self):
        prof = self.profiler()
        prof.enable()
        f(self.DURATION / 2, self.NCALLS)
        prof.disable()
        prof.enable()
        f(self.DURATION / 2, self.NCALLS)
        prof.disable()
        prof.create_stats()
        self.check_stats(prof.stats, 2)

    def test_runcall(self):
        prof = self.profiler()
        prof.runcall(f, self.DURATION, ncalls=self.NCALLS)
        prof.create_stats()
        self.check_stats(prof.stats)

    def test_run(self):
        import __main__
        __main__.some_global_name = f
        prof = self.profiler()
        prof.run("some_global_name(%r, %r)" % (self.DURATION, self.NCALLS))
        prof.create_stats()
        self.check_stats(prof.stats)

    def test_runctx(self):
        prof = self.profiler()
        prof.runctx("f(duration, ncalls)",
                    dict(f=f),
                    dict(duration=self.DURATION, ncalls=self.NCALLS))
        prof.create_stats()
        self.check_stats(prof.stats)

    def test_pstats(self):
        prof = self.profiler()
        prof.runcall(f, self.DURATION, ncalls=self.NCALLS)

        tt, ct = self.check_in_pstats(prof, run_until, ncalls=self.NCALLS)
        self.assertLessEqual(ct, self.DURATION * 1.5)
        self.assertGreaterEqual(ct, self.DURATION * 0.8)

    def test_finalizer(self):
        prof = mtprof.Profile()
        prof.close()
        prof = mtprof.Profile()
        del prof
        gc.collect()
        prof = mtprof.Profile()
        prof.close()


if __name__ == "__main__":
    unittest.main()
