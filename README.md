<p align="center">

<img width="400" src="https://s3.ap-south-1.amazonaws.com/saral-data-bucket/misc/logo%2Btype%2Bnocatch.svg" />

[![PyPI](https://img.shields.io/pypi/pyversions/zproc.svg?style=for-the-badge)](https://pypi.org/project/zproc/)

<p align="center">

# The idea

ZProc is an experiment that aims to unify how we program multitasking and distributed applications.

If it succeeds, programmers can have a _single_ method to program in this general area of computing, at any level in the stack.

---

Perhaps, the ethos of this project is best summarised by this quote from the late Joe Armstrong:

> I want one way to program, not many.

# Implemenatation

The current solution is a centralized one. 

At the heart lies a Python program, 
that serves a data structure (A python dict), 
which supports event sourcing, time travel, task sequencing, etc.

Processes simply mutate this remote data structure, and communicate using the events it emitts.

And it does this using [zeromq](http://zeromq.org/) — in a way that users don't need to concern themselves with the intricacies of networking and messaing passing — while still benifiting from the powers of [CSP](https://en.wikipedia.org/wiki/Communicating_sequential_processes).

This project is currently understood to be at [TRL3](https://en.wikipedia.org/wiki/Technology_readiness_level).
