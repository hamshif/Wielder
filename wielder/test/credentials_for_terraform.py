#!/usr/bin/env python
import logging
from os.path import expanduser

from wield_services.wield.deploy.configurer import get_project_deploy_mode
from wield_services.wield.log_util import setup_logging

from wielder.util.credential_helper import get_aws_mfa_cred_command
from wielder.util.util import DirContext

# TODO use logging and recheck what we are testing

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    wield_mode, conf, action = get_project_deploy_mode()

    cred_string = get_aws_mfa_cred_command(conf.terraformer.super_cluster.cred_role)

    print(cred_string)

    _home = expanduser("~")
    print(_home)
    dir_path = f"{_home}/stam/pep_eks"

    with DirContext(_home):

        cmd = f'{cred_string}\nterraform plan'

        print(cmd)
