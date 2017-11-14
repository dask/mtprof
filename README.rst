mtprof
======

A multi-thread aware profiler package, with an API similar to that
of the standard ``cProfile`` module.

Compatibility
-------------

Python 3 is required, and only POSIX systems (Linux, etc.) are currently
supported.

Limitations
-----------

Due to the way Python profiling works, ``mtprof`` is only able to exploit
profiling stats from threads whose lifetime is a subset of the profiler's
lifetime.  A thread started before profiling was started, or ended after
profiling was stopped, cannot have its statistics collected.

Due to this limitation, it is probably easier to use the command-line
interface, which is similar to that of ``cProfile``: just run
``python -m mtprof --help`` to get a view of the available options.

Only threads created using the standard ``threading.Thread`` interface
are recognized.  For most use cases this should not be an issue.

Status
------

This package is experimental.
