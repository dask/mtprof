import gc
import io
import logging
import os
import pstats
import sys
import subprocess
import threading
import tempfile
import time
import timeit
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
    """
    Test internal functions
    """
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

    def get_function_repr(self, func, strip_dirs=False):
        try:
            code = func.__code__
        except AttributeError:
            raise
        else:
            # filename:lineno(function)
            filename = code.co_filename
            if strip_dirs:
                filename = os.path.basename(filename)
            return "%s:%d(%s)" % (filename, code.co_firstlineno, code.co_name)

    def check_function(self, stats, func):
        key = self.get_function_key(func)
        self.assertIn(key, stats, sorted(stats))
        return stats[key]

    def check_in_pstats_output(self, lines, func, ncalls, strip_dirs=True):
        """
        Given *lines* output by pstats, check that *func* is mentioned
        with *ncalls* total function calls.
        """
        look_for = self.get_function_repr(func, strip_dirs)
        for line in lines:
            parts = line.strip().split()
            if parts and parts[-1] == look_for:
                break
        else:
            self.fail("could not find %r in %r" % (look_for, lines))
        nc, tt, percall, ct, cumpercall = parts[:5]
        nc = int(nc.partition('/')[0])
        tt = float(tt)
        ct = float(ct)
        self.assertEqual(nc, ncalls)
        return tt, ct

    def check_in_pstats(self, pstats_arg, func, ncalls):
        sio = io.StringIO()
        st = pstats.Stats(pstats_arg, stream=sio)
        st.sort_stats('cumtime').print_stats(20)
        return self.check_in_pstats_output(sio.getvalue().splitlines(),
                                           func, ncalls,
                                           strip_dirs=False)


class TestSingleThread(BaseProfilingTest, unittest.TestCase):
    """
    Single-thread tests of the Python API.
    """
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


class TestCLI(BaseProfilingTest, unittest.TestCase):

    def run_cli(self, args, retcode=0):
        command = [sys.executable, '-m', 'mtprof'] + args
        proc = subprocess.run(command, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, universal_newlines=True,
                              timeout=10)
        if proc.returncode != retcode:
            print("------- Process stdout --------")
            print(proc.stdout)
            print("------- Process stderr --------")
            print(proc.stderr)
            self.assertEqual(proc.returncode, retcode)
        return proc

    def make_tempfile(self, suffix=None):
        fd, name = tempfile.mkstemp(prefix='test_mprof_', suffix=suffix)
        os.close(fd)
        self.addCleanup(os.unlink, name)
        return name

    def timeit_args(self):
        timeit_args = ['-n', '800', '-r', '2',
                       '-s', 'import logging', 'logging.getLogger("foo")']
        return timeit_args

    def timeit_check(self, lines):
        self.check_in_pstats_output(lines, logging.getLogger, 1600)

    def test_basic(self):
        proc = self.run_cli([], retcode=2)
        proc = self.run_cli(['-m'], retcode=2)

    def test_timeit_module(self):
        """
        python -m mtprof -m timeit ...
        """
        proc = self.run_cli(['-m', 'timeit'] + self.timeit_args())
        self.timeit_check(proc.stdout.splitlines())
        self.assertFalse(proc.stderr)

    def test_timeit_script(self):
        """
        python -m mtprof /xxx/timeit.py ...
        """
        proc = self.run_cli([timeit.__file__] + self.timeit_args())
        self.timeit_check(proc.stdout.splitlines())
        self.assertFalse(proc.stderr)

    def test_outfile(self):
        outfile = self.make_tempfile(suffix='.prof')
        proc = self.run_cli(['-o', outfile, '-m', 'timeit'] + self.timeit_args())
        self.assertFalse(proc.stderr)

        sio = io.StringIO()
        stats = pstats.Stats(outfile, stream=sio)
        stats.strip_dirs()
        stats.sort_stats('time')
        stats.print_stats(30)
        self.timeit_check(sio.getvalue().splitlines())


if __name__ == "__main__":
    unittest.main()
