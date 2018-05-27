#!/usr/bin/env python

import subprocess as sp


def async_cmd(args, verbose=False):
    lines = []
    p = sp.Popen(args, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT)
    for line in p.stdout.readlines():
        if verbose:
            print(line.decode("utf-8"))
        lines.append(line.decode("utf-8"))

    return_val = p.wait()
    print(return_val)
    return lines


def subprocess_cmd(command):
    process = sp.Popen(command,stdout=sp.PIPE, shell=True)
    proc_stdout = process.communicate()[0].strip()
    print(proc_stdout)


if __name__ == "__main__":

    subprocess_cmd('echo a; echo b')

