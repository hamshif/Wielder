#!/usr/bin/env python
import logging
import os
import re
from time import sleep
import random
import string
import yaml
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


def write_action_report(name, value):

    dir_path = '/tmp/actions'
    os.makedirs(dir_path, exist_ok=True)

    report_path = f'{dir_path}/actions_report.yaml'

    actions = {}

    if os.path.isfile(report_path):
        with open(report_path) as f:
            actions = yaml.load(f, Loader=yaml.FullLoader)

    actions[name] = value

    report = yaml.dump(actions)

    with open(report_path, 'wt') as file_out:
        file_out.write(report)


def get_pod_env_var_value(namespace, pod, var_name):

    reply = async_cmd(f'kubectl exec -it -n {namespace} {pod} printenv')

    for var in reply:

        tup = var.split('=')

        if len(tup) > 1:
            logging.debug(f'{tup[0]}  :  {tup[1]}')

            if tup[0] == var_name:

                return tup[1]


def get_pod_actions(namespace, pod_name):

    report_path = '/tmp/actions/actions_report.yaml'

    reply = async_cmd(f'kubectl exec -it -n {namespace} {pod_name} cat {report_path}')

    logging.debug(f'Kubectl reply is:\n{reply}')

    actions = {}

    for ac in reply:

        try:
            action = yaml.safe_load(ac)
            actions.update(action)
        except Exception as e:
            logging.debug(str(e))
            logging.warning(f"List value {ac} can't be parsed as yaml")

    logging.debug(actions)

    return actions


def block_for_action(namespace, pod, var_name, expected_value, slumber=5, _max=10):
    """
    This method is a primitive polling mechanism to make sure a pod has completed an assignment.
    It assumes the pod has written a Yaml action to a file and attempts to read it.
    :param namespace: Pod namespace
    :type namespace: str
    :param pod: The pod name
    :type pod: str
    :param var_name: action name
    :type var_name: str
    :param expected_value: the expected action value
    :type expected_value: str
    :param slumber: time to sleep between polling tries, defaults to 5
    :type slumber: int
    :param _max: Max polling attempts
    :type _max: int
    :return: if the ction value was as expected
    :rtype: bool
    """

    for i in range(_max):

        try:
            actions = get_pod_actions(namespace, pod)

            var_value = actions[var_name]

            logging.debug(f'var_name {var_name} value is: {var_value}, expected value: {expected_value}')

            if var_value is not None and var_value == expected_value:
                return True
            else:
                logging.info(f'var_name is {var_name} var_value is {var_value}')

        except Exception as e:
            logging.error("Error getting action from pod", e)

        logging.debug(f'sleeping {i} of {_max} for {slumber}')
        sleep(slumber)

    return False


def get_random_string(length):
    letters = string.ascii_lowercase
    result_str = ''.join(random.choice(letters) for i in range(length))
    print("Random string of length", length, "is:", result_str)

    return result_str


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _ip = get_external_ip()

    _line = 'Do not yell in open space'

    _dir_path = os.path.dirname(os.path.realpath(__file__))
    logging.debug(f"current working dir: {_dir_path}")

    full_path = f'{_dir_path}/punishment.conf'

    for a in range(100):
        line_prepender(full_path, _line, once=False)

    logging.debug('break point')

    remove_line(full_path, _line)




