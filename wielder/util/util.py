#!/usr/bin/env python
import logging
import os
import re
from requests import get

from wielder.util.commander import async_cmd

# This example requires the requests library be installed.  You can learn more
# about the Requests library here: http://docs.python-requests.org/en/latest/
from wielder.util.log_util import setup_logging


def get_kube_context():

    context = async_cmd('kubectl config current-context')[0][:-1]

    return context


def get_external_ip():

    try:
        ip = get('https://api.ipify.org').text
    except Exception as e:
        logging.error(str(e))
    else:
        ip = 'couldnt get ip'

    logging.info(f'My public IP address is:{ip}')
    return ip


class DirContext:
    """
    Written by Ido Goodis
    Context manager for changing the current working directory
    """

    def __init__(self, newPath):
        self.newPath = os.path.expanduser(newPath)

    def __enter__(self):
        self.savedPath = os.getcwd()
        os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        os.chdir(self.savedPath)


def replace_last(full, sub, rep=''):
    """
    replaces the last instance of a substring in the full string with rep
    :param full: the base string in which the replacement should happen
    :param sub: to be replaced
    :param rep: replacement substring default empty
    :return:
    """

    end = ''
    count = 0
    for c in reversed(full):
        count = count + 1
        end = c + end

        if sub in end:
            return full[:-count] + end.replace(sub, rep)

    return full


def purge(directory, pattern):

    for f in os.listdir(directory):
        if re.search(pattern, f):
            os.remove(os.path.join(directory, f))


def is_line_in_file(full_path, line):

    with open(full_path) as f:
        content = f.readlines()

        for l in content:
            if line in l:
                f.close()
                return True

        return False


def line_prepender(filename, line, once=True):

    with open(filename, 'r+') as f:
        content = f.read()
        f.seek(0, 0)

        if once and is_line_in_file(filename, line):
            return

        f.write(line.rstrip('\r\n') + '\n' + content)


def remove_line(filename, line):

    f = open(filename, "r+")
    d = f.readlines()
    f.seek(0)
    for i in d:
        if line not in i:
            f.write(i)
    f.truncate()
    f.close()


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _ip = get_external_ip()

    _line = 'Do not yell in open space'

    dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {dir_path}")

    full_path = f'{dir_path}/punishment.conf'

    for a in range(100):
        line_prepender(full_path, _line, once=False)

    logging.debug('break point')

    remove_line(full_path, _line)




