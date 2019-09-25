#!/usr/bin/env python

import subprocess as sp
import shlex


def async_cmd(args, verbose=False, executable='/bin/sh'):
    lines = []
    p = sp.Popen(args, shell=True, stdout=sp.PIPE, stderr=sp.STDOUT, executable=executable)
    for line in p.stdout.readlines():
        if verbose:
            print(line.decode("utf-8"))
        lines.append(line.decode("utf-8"))

    return_val = p.wait()
    print(return_val)
    return lines


def subprocess_cmd(command, executable='/bin/sh'):
    process = sp.Popen(command, stdout=sp.PIPE, shell=True, executable=executable)
    proc_stdout = process.communicate()[0].strip()
    print(proc_stdout)


def bash_command(command, shell=False):
    try:
        output = sp.check_output(command, shell=shell, stderr=sp.STDOUT, universal_newlines=True)
        return output.strip()
    except Exception as e:
        raise Exception(f"Error occurred while trying to run bash command: {e}")


def cmd_for_return_code(command):
    """
    Runs a linux shell command and:
    1. Ignores standard output.
    2. Listens for errors.
    3. Waits for return code.
    :param command: compound Linux command
    :return: return code.
    """

    args = shlex.split(command)

    # p = sp.Popen(args, stdout=sp.PIPE, stderr=sp.PIPE)

    p = sp.Popen(args, stderr=sp.PIPE)

    output, err = p.communicate()
    print(f'output: {output}')
    print(f'err: {err}')

    rc = p.returncode

    print(f'Shell return code: {rc}')

    return rc


if __name__ == "__main__":

    a = async_cmd('/usr/local/bin/kubectl config current-context')
    print(a)

    a = async_cmd('kubectl config current-context')
    print(a)
    # subprocess_cmd('echo a; echo b')

    a = async_cmd('docker images | grep dev | grep perl;')
    print(a)

