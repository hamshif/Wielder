#!/usr/bin/env python
import json
import logging
import os
from os.path import expanduser

from wield_services.wield.deploy.configurer import get_project_deploy_mode
from wield_services.wield.log_util import setup_logging

from wielder.util.util import DirContext


def as_export_cmd(prop_dict):

    a = ''

    for key, value in prop_dict.items():
        a = a + f'export {key}="{value}";\n'

    return a


def get_aws_mfa_cred_command(role_name):
    """
    Looks for aws MFA session credentials file,
    extracts env variables necessary for running terraform
    :param role_name: role name to check against CLI MFA cache.
    :return: returns env credential shell command or empty string.
    """

    home = expanduser("~")
    print(home)
    dir_path = f"{home}/.aws/cli/cache"

    env_cred = {}

    for subdir, dirs, files in os.walk(dir_path):

        for f in files:
            print(f": \n{f}")

            if not f.endswith('.json'):
                continue

            with open(f'{dir_path}/{f}') as json_file:
                data = json.load(json_file)

                j = json.dumps(data, indent=2, sort_keys=True)
                print(j)

                cred = data["Credentials"]

                print("\n=======\n")

                if "AssumedRoleUser" in data.keys():

                    if "Arn" in data["AssumedRoleUser"].keys():

                        if f'/{role_name}/' not in data["AssumedRoleUser"]["Arn"]:
                            continue

                        env_cred["ASSUMED_ROLE"] = data["AssumedRoleUser"]["AssumedRoleId"]
                        env_cred["AWS_ACCESS_KEY_ID"] = cred["AccessKeyId"]
                        env_cred["AWS_SECRET_ACCESS_KEY"] = cred["SecretAccessKey"]
                        env_cred["AWS_SESSION_TOKEN"] = cred["SessionToken"]
                        env_cred["AWS_SECURITY_TOKEN"] = cred["SessionToken"]

                        break

    as_string_cmd = as_export_cmd(env_cred)

    if not as_string_cmd:

        print("couldn't find credentials returning empty string")

    return as_string_cmd


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    wield_mode, conf, action = get_project_deploy_mode()

    # import boto3
    # s3client = boto3.client('s3')
    # response = s3client.list_buckets()['Buckets']

    cred_string = get_aws_mfa_cred_command(conf.terraformer.super_cluster.cred_role)

    # print(cred_string)

    _home = expanduser("~")
    print(_home)
    dir_path = f"{_home}/stam/pep_eks"

    with DirContext(_home):

        cmd = f'{cred_string}\nterraform plan'

        print(cmd)






