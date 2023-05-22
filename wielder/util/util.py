#!/usr/bin/env python
import logging
import os
import random
import re
import string
from time import sleep

import shutil
import boto3
import yaml
from pyhocon import ConfigFactory
from requests import get
from wielder.util.commander import async_cmd
# This example requires the requests library be installed.  You can learn more
# about the Requests library here: http://docs.python-requests.org/en/latest/
from wielder.util.credential_helper import get_aws_mfa_cred
from wielder.util.log_util import setup_logging


def convert_path_to_any_os(path):
    return path.replace('/', os.sep)


def convert_to_unix_path(path):
    return os.path.normpath(path).replace("\\", "/")


def get_external_ip():
    try:
        ip = get('https://api.ipify.org').text
    except Exception as e:
        logging.error(str(e))
    else:
        ip = "couldn't get ip"

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


def write_action_report(name, value):
    dir_path = '/tmp/actions'
    makedirs(dir_path, exist_ok=True)

    report_path = f'{dir_path}/actions_report.yaml'

    actions = {}

    if os.path.isfile(report_path):
        with open(report_path) as f:
            actions = yaml.load(f, Loader=yaml.FullLoader)

    actions[name] = value

    report = yaml.dump(actions)

    with open(report_path, 'wt') as file_out:
        file_out.write(report)


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    print("Random string of length", length, "is:", result_str)

    return result_str


def get_aws_session(conf):
    role = conf.aws_cred_role

    cred = get_aws_mfa_cred(role)

    session = boto3.Session(
        aws_access_key_id=cred["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=cred["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=cred["AWS_SESSION_TOKEN"],
        profile_name=conf.aws_profile,
        region_name=conf.aws_zone
    )

    return session


def create_pyenv(name, py_version):
    wield_path = get_wield_root()

    _cmd = f'{wield_path}/scripts/create_pyenv.bash {name}'

    response = async_cmd(_cmd)

    for st in response:
        print(st)

    done = response[-1][:-1]

    if done == 'floobatzky':
        created = True
    else:
        created = False

    return created


def get_wield_root():
    dir_path = os.path.dirname(os.path.realpath(__file__))

    i = dir_path.rindex('/')

    dir_path = dir_path[:i]

    return dir_path


def block_for_file(why, full_path, interval, max_attempts=50):
    for i in range(max_attempts):

        print(f'Attempt {i} of {max_attempts}, Sleeping {interval} to check if file {full_path} was created.\n{why}')
        sleep(interval)

        if os.path.isfile(full_path):
            return


def pretty(conf):

    logging.info('Showing top level config items')

    [print(it) for it in conf.as_plain_ordered_dict().items()]


def makedirs(path, exist_ok=True):
    if os.name == 'nt':
        path = convert_path_to_any_os(path)
    os.makedirs(path, exist_ok=exist_ok)


def copyfile(unique_context_conf, dest):
    if os.name == 'nt':
        unique_context_conf = convert_path_to_any_os(unique_context_conf)
        dest = convert_path_to_any_os(dest)
    shutil.copyfile(unique_context_conf, dest)


def copytree(source, destination):
    if os.name == 'nt':
        source = convert_path_to_any_os(source)
        destination = convert_path_to_any_os(destination)
    shutil.copytree(source, destination)


def isfile(src):
    if os.name == 'nt':
        src = convert_path_to_any_os(src)
    return os.path.isfile(src)


def remove(stale):
    if os.name == 'nt':
        stale = convert_path_to_any_os(stale)
    os.remove(stale)


def copy(src, dest):
    if os.name == 'nt':
        src = convert_path_to_any_os(src)
        dest = convert_path_to_any_os(dest)
    shutil.copy(src, dest)


def exists(dest):
    if os.name == 'nt':
        dest = convert_path_to_any_os(dest)
    return os.path.exists(dest)


def rmtree(dest, ignore_errors=True):
    if os.name == 'nt':
        dest = convert_path_to_any_os(dest)
    shutil.rmtree(dest, ignore_errors=ignore_errors)


def open(place_holder, open_purpose):
    if os.name == 'nt':
        place_holder = convert_path_to_any_os(place_holder)
    return open(place_holder, open_purpose)


def parse_file(full_path):
    if os.name == 'nt':
        full_path = convert_path_to_any_os(full_path)
    return ConfigFactory.parse_file(full_path)

def walk(source):
    if os.name == 'nt':
        source = convert_path_to_any_os(source)
    return os.walk(source)

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    create_pyenv('shnee', '3.8.7')

    _ip = get_external_ip()

    _line = 'Do not yell in open space'

    _dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {_dir_path}")

    _full_path = f'{_dir_path}/punishment.conf'

    for a in range(100):
        line_prepender(_full_path, _line, once=False)

    logging.debug('break point')

    remove_line(_full_path, _line)