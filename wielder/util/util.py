#!/usr/bin/env python
import logging
import os
import pathlib
import random
import re
import string
from time import sleep
from contextlib import contextmanager

import shutil
import boto3
import yaml
from pyhocon import ConfigFactory
from requests import get
from wielder.util.commander import async_cmd
# This example requires the requests library be installed.  You can learn more
# about the Requests library here: http://docs.python-requests.org/en/latest/
from wielder.util.credential_helper import aws_mfa_cred_as_boto3_session_kwargs
from wielder.util.log_util import setup_logging


import platform
import subprocess
import json

def get_local_system() -> str:
    """Returns windows, mac, wsl, or ubuntu."""
    if os.name == 'nt':
        return 'windows'
    elif platform.system().lower() == 'darwin':
        return 'mac'
    elif platform.system().lower() == 'linux':
        try:
            if 'microsoft-standard' in os.uname().release.lower():
                return 'wsl'
        except Exception:
            pass
        return 'ubuntu'
    return 'unknown'


def get_local_docker_flavor() -> str:
    """
    Returns a strict description of the locally reachable Docker engine topology.
    The intent is to differentiate materially different builder behaviors, especially
    inside WSL where Docker Desktop and a native Linux daemon are not equivalent.
    """
    try:
        context = subprocess.check_output(
            ["docker", "context", "show"],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        info_raw = subprocess.check_output(
            ["docker", "info", "--format", "{{json .}}"],
            stderr=subprocess.STDOUT,
            text=True,
        ).strip()
        info = json.loads(info_raw)
    except Exception as exc:
        raise RuntimeError("Failed to inspect local Docker engine topology.") from exc

    operating_system = str(info.get("OperatingSystem", "")).lower()
    platform_name = str(info.get("ClientInfo", {}).get("Platform", {}).get("Name", "")).lower()
    daemon_name = str(info.get("Name", "")).lower()

    if (
        context in {"desktop-linux", "docker-desktop"}
        or "docker desktop" in operating_system
        or "docker desktop" in platform_name
        or daemon_name == "docker-desktop"
    ):
        return "docker_desktop"

    if operating_system.startswith("ubuntu") or operating_system.startswith("debian"):
        return "native_linux"

    raise NotImplementedError(
        f"Unsupported or ambiguous local Docker flavor. "
        f"context=[{context}] operating_system=[{operating_system}] platform=[{platform_name}] daemon=[{daemon_name}]"
    )

def get_os_host_mount_prefix(system_name: str) -> str:
    """
    Returns the host volumetric mount prefix depending on the local system architecture.
    """
    if system_name == 'wsl':
        # Docker Desktop's Kubelet runs directly inside containerd over a separate Linux VM.
        # It natively DOES NOT parse `//wsl.localhost/` UNC mappings properly or map user home drives.
        # Relying on Microsoft's strict `/mnt/wsl` tmpfs guarantees shared cross-VM persistent volume access.
        return "/mnt/wsl"
    return ""


def get_native_os_path(path: str, system_name: str = None) -> str:
    """
    Reverts cross-boundary path translations natively back into the local environment execution scope natively.
    """
    if system_name is None:
        system_name = get_local_system()

    # The paths target the natively shared /mnt/wsl boundary directly across the VM namespace.
    return path


def get_whoami():
    import socket
    import getpass
    
    try:
        user = getpass.getuser()
    except Exception:
        user = "unknown_user"
        
    try:
        machine = socket.gethostname()
    except Exception:
        machine = "unknown_machine"
        
    return user, machine


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

    profile_name = str(conf.aws_profile).strip() or None
    region_name = conf.aws_zone
    session_kwargs = aws_mfa_cred_as_boto3_session_kwargs(role)

    if not session_kwargs:
        session_kwargs["profile_name"] = profile_name
    session_kwargs["region_name"] = region_name

    session = boto3.Session(**session_kwargs)

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


def wopen(path, *args, **kwargs):
    # expands ~ and env vars and makes it OS-portable
    if os.name == 'nt':
        path = convert_path_to_any_os(path)
    return open(path, *args, **kwargs)


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


def isdir(src):
    if os.name == 'nt':
        src = convert_path_to_any_os(src)
    return os.path.isdir(src)


def remove(stale, ignore_errors=True):

    if ignore_errors and not exists(stale):
        return
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


def parse_file_as_hocon(full_path):
    if os.name == 'nt':
        full_path = convert_path_to_any_os(full_path)
    return ConfigFactory.parse_file(full_path)


def walk(source):
    if os.name == 'nt':
        source = convert_path_to_any_os(source)
    return os.walk(source)


def get_files_in_dir(full_path):

    # list all the files in directory
    if os.name == 'nt':
        full_path = convert_path_to_any_os(full_path)

    return os.listdir(full_path)


def open_data_path(full_path, mode='r'):
    if os.name == 'nt':
        full_path = convert_path_to_any_os(full_path)
    return open(full_path, mode)


def dirname(full_path):
    if os.name == 'nt':
        full_path = convert_path_to_any_os(full_path)
    return os.path.dirname(full_path)

@contextmanager
def wu_open(*args, **kwargs):

    if os.name == 'nt':
        arg = args[0]
        unix_path = convert_path_to_any_os(arg)
        # replace the first argument with the converted path
        args = (unix_path,) + args[1:]

    file = open(*args, **kwargs)
    try:
        yield file
    finally:
        file.close()


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
