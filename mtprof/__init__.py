import collections
import cProfile
import functools
import os
import profile as _pyprofile
import pstats
import sys
import threading
import traceback
import time
import warnings
import weakref


def _default_timer():
    if os.name == 'posix':
        return functools.partial(time.clock_gettime, time.CLOCK_THREAD_CPUTIME_ID)
    else:
        raise NotImplementedError("per-thread CPU timer unavailable on this system")


_real_bootstrap_inner = threading.Thread._bootstrap_inner

def _bootstrap_inner(hook, thread):
    assert isinstance(hook, _ThreadProfilingHook)
    hook._bootstrap_inner(thread)


class _ThreadProfilingHook:

    def __init__(self, mtprofiler):
        self._mtprofiler = weakref.ref(mtprofiler)

    def _bootstrap_inner(self, thread):
        try:
            assert isinstance(thread, threading.Thread)
            prof = self._mtprofiler()
            if prof is not None:
                prof._run_thread(thread,
                                 functools.partial(_real_bootstrap_inner, thread))
            else:
                _real_bootstrap_inner(thread)
        except SystemExit:
            pass

    def _enable_hook(self):
        assert threading.Thread._bootstrap_inner is _real_bootstrap_inner, "some thread hook already enabled"
        threading.Thread._bootstrap_inner = lambda thread_inst: _bootstrap_inner(self, thread_inst)

    def _disable_hook(self):
        assert threading.Thread._bootstrap_inner is not _real_bootstrap_inner, "thread hook not enabled"
        threading.Thread._bootstrap_inner = _real_bootstrap_inner


class _MTProfiler:
    _mt_hook = None

    def __init__(self, timer=None, *, profiler_class=cProfile.Profile, **kwargs):
        self._timer = timer or _default_timer()
        self._partial_stats = []
        self._profiler_factory = functools.partial(profiler_class, self._timer, **kwargs)

        self._enabled = False
        self._main_profiler = self._profiler_factory()
        self._main_tid = None
        self._thread_profilers = {}
        self._lock = threading.Lock()

        self._mt_hook = _ThreadProfilingHook(self)
        self._mt_hook._enable_hook()
        self._finalizer = weakref.finalize(self, self._mt_hook._disable_hook)

    def _add_partial_stats(self, stats):
        self._partial_stats.append(stats)

    def _merge_stats(self, lst):
        merged = {}
        for stats in lst:
            for func, func_stats in stats.items():
                cur = merged.get(func)
                if cur is not None:
                    merged[func] = pstats.add_func_stats(cur, func_stats)
                else:
                    merged[func] = func_stats
        return merged

    def _run_thread(self, thread, func):
        with self._lock:
            if self.enabled:
                prof = self._profiler_factory()
                self._thread_profilers[thread] = prof
                prof.enable()
            else:
                prof = None
        try:
            func()
        finally:
            if prof is not None:
                prof.disable()
                del self._thread_profilers[thread]
                prof.create_stats()
                self._add_partial_stats(prof.stats)

    # create_stats() and the `stats` attribute are part of the pstats contract

    def create_stats(self):
        self.disable()
        running_threads = sorted(self._thread_profilers, key=lambda t: t.name)
        # We cannot enable / disable profilers from another thread,
        # and calling create_stats() from another thread crashes _lsprof.
        # So we can only warn about still running threads.
        if running_threads:
            warnings.warn("Profiling will omit still running threads: %s"
                          % (running_threads,), RuntimeWarning)

        self._main_profiler.create_stats()
        self.stats = self._merge_stats([self._main_profiler.stats] + self._partial_stats)

    # Public API

    def close(self):
        self._finalizer()

    @property
    def enabled(self):
        return self._enabled

    def enable(self):
        with self._lock:
            if not self._enabled:
                self._main_profiler.enable()
                self._main_tid = threading.get_ident()
                self._enabled = True

    def disable(self):
        with self._lock:
            if self._enabled:
                if threading.get_ident() != self._main_tid:
                    raise RuntimeError("enable() and disable() should be "
                                       "called from the same thread")
                self._main_profiler.disable()
                self._enabled = False

    def run(self, cmd):
        import __main__
        dict = __main__.__dict__
        return self.runctx(cmd, dict, dict)

    def runctx(self, cmd, globals, locals):
        self.enable()
        try:
            self._main_profiler.runctx(cmd, globals, locals)
        finally:
            self.disable()
        return self

    def runcall(self, func, *args, **kw):
        self.enable()
        try:
            return self._main_profiler.runcall(func, *args, **kw)
        finally:
            self.disable()

    def print_stats(self, sort=-1):
        pstats.Stats(self).strip_dirs().sort_stats(sort).print_stats()

    def dump_stats(self, file):
        import marshal
        with open(file, 'wb') as f:
            self.create_stats()
            marshal.dump(self.stats, f)


Profile = _MTProfiler


# ____________________________________________________________
# Simple interface

def run(statement, filename=None, sort=-1):
    return _pyprofile._Utils(Profile).run(statement, filename, sort)

def runctx(statement, globals, locals, filename=None, sort=-1):
    return _pyprofile._Utils(Profile).runctx(statement, globals, locals,
                                             filename, sort)

run.__doc__ = _pyprofile.run.__doc__
runctx.__doc__ = _pyprofile.runctx.__doc__
