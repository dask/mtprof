import argparse
import os
import runpy
import sys

from . import runctx, Profile

# ____________________________________________________________

def main():
    parser = argparse.ArgumentParser(
        prog='mtperf.py',
        description="Profile a Python module or application")
    parser.add_argument('-o', '--outfile', dest="outfile",
                        help="Save stats to <outfile>")
    parser.add_argument('-s', '--sort', dest="sort",
                        help="Sort order when printing to stdout, "
                             "based on pstats.Stats class",
                        default=-1)

    parser.add_argument('-m', dest="module", action='store_true',
                        help="Profile a library module")
    parser.add_argument('script_or_module',
                        help="Script or module to profile")

    parser.add_argument('args', nargs=argparse.REMAINDER,
                        help="Additional arguments for script or module")

    args = parser.parse_args()

    prof = Profile()
    if args.module:
        module_name = args.script_or_module
        sys.argv[:] = [module_name] + args.args
        prof.enable()
        try:
            runpy.run_module(module_name, run_name='__main__')
        except SystemExit:
            pass
        finally:
            prof.disable()
    else:
        script_name = args.script_or_module
        sys.argv[:] = [script_name] + args.args
        sys.path.insert(0, os.path.dirname(script_name))
        with open(script_name, 'rb') as fp:
            code = compile(fp.read(), script_name, 'exec')
        globs = {
            '__file__': script_name,
            '__name__': '__main__',
            '__package__': None,
            '__cached__': None,
        }
        prof.enable()
        try:
            exec(code, globs, None)
        except SystemExit:
            pass
        finally:
            prof.disable()

    # XXX use an atexit hook instead, to make sure all non-daemon
    # threads are terminated?
    prof.create_stats()
    if args.outfile:
        prof.dump_stats(args.outfile)
    else:
        prof.print_stats(args.sort)


# When invoked as main program, invoke the profiler on a script
if __name__ == '__main__':
    main()
