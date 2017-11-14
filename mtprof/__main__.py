from optparse import OptionParser
import os
import runpy
import sys

from . import runctx, Profile

# ____________________________________________________________

def main():
    # XXX convert to argparse
    usage = "cProfile.py [-o output_file_path] [-s sort] [-m module | scriptfile] [arg] ..."
    parser = OptionParser(usage=usage)
    parser.allow_interspersed_args = False
    parser.add_option('-o', '--outfile', dest="outfile",
        help="Save stats to <outfile>", default=None)
    parser.add_option('-s', '--sort', dest="sort",
        help="Sort order when printing to stdout, based on pstats.Stats class",
        default=-1)
    parser.add_option('-m', dest="module", action="store_true",
        help="Profile a library module", default=False)

    if not sys.argv[1:]:
        parser.print_usage()
        sys.exit(2)

    (options, args) = parser.parse_args()

    if len(args) > 0:
        sys.argv[:] = args

        prof = Profile()
        if options.module:
            prof.enable()
            try:
                runpy.run_module(args[0], run_name='__main__')
            except SystemExit:
                pass
            finally:
                prof.disable()
        else:
            progname = args[0]
            sys.path.insert(0, os.path.dirname(progname))
            with open(progname, 'rb') as fp:
                code = compile(fp.read(), progname, 'exec')
            globs = {
                '__file__': progname,
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

        prof.create_stats()
        if options.outfile:
            prof.dump_stats(options.outfile)
        else:
            prof.print_stats(options.sort)

    else:
        parser.print_usage()
    return parser


# When invoked as main program, invoke the profiler on a script
if __name__ == '__main__':
    main()
