#!/usr/bin/env python

from setuptools import setup, find_packages


with open('requirements.txt') as f:
    requires = [line.strip() for line in f.read().splitlines()]
    requires = [line for line in requires if line and not line.startswith('#')]

with open('README.rst') as f:
    long_description = f.read()


setup(name='mtprof',
      version='0.0.1',
      description='Thread-aware profiler',
      #url='https://xxx.readthedocs.io/en/latest/',
      maintainer='Antoine Pitrou',
      maintainer_email='antoine@python.org',
      license='BSD',
      packages=find_packages(),
      long_description=long_description,
      classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: POSIX",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development",
      ],
      )
