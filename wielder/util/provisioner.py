#!/usr/bin/env python
import json
import logging
import os
import random

from data_common.config.configurer import get_conf
from wielder.util.commander import subprocess_cmd as _cmd, subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.util.templater import config_to_terraform
from wielder.util.util import DirContext
from wielder.wield.enumerator import TerraformAction, wield_to_terraform, WieldAction


class WrapTerraform:

    def __init__(self, tf_path, unique_name=None):
        """

        :param tf_path: The path to the terraform root
        :type tf_path: str
        :param unique_name: Name of state if state is stored in a backend e.g. S3 bucket defaults to None.
        :type unique_name: str
        """

        self.tf_path = tf_path
        self.unique_name = unique_name

    def cmd(self, terraform_action=TerraformAction.PLAN, auto_approve=True):

        action = terraform_action.value

        with DirContext(self.tf_path):

            cmd1 = f'terraform {action}'

            if terraform_action == TerraformAction.INIT and self.unique_name is not None:
                cmd1 = f'{cmd1} -backend-config "prefix=terraform/state/{self.unique_name}"'
            if auto_approve and (terraform_action == TerraformAction.DESTROY or terraform_action == TerraformAction.APPLY):
                cmd1 = f'{cmd1} -auto-approve'

            logging.debug(f"Running:\n{cmd1}")
            os.system(cmd1)

    def configure_terraform(self, tree, new_state=False):
        """
        Converts a Hocon configuration to Terraform in the path
        :param tree: Hocon configuration to be translated to terraform.tfvars file
        :type tree: Hocon Config Tree
        :param new_state:
        :type new_state: bool
        :return:
        :rtype:
        """

        if new_state:
            logging.debug("Trying to remove local terraform state files if they exist")
            r = random.randint(3, 10000)
            full = f'{self.tf_path}/terraform.tfstate'
            _cmd(f"mv {full} {full}.{r}.copy")

        config_to_terraform(
            tree=tree,
            destination=self.tf_path,
            print_vars=True
        )

    def state(self, verbose=True):

        with DirContext(self.tf_path):

            state_bytes = subprocess_cmd('terraform show -json terraform.tfstate')

            state_json = state_bytes.decode('utf8')
            state = json.loads(state_json)

            if verbose:
                s = json.dumps(state, indent=4, sort_keys=True)
                logging.debug(s)

            return state


def provision_terraform(resource_type, provision_root, tree, runtime_env, action, just_state=False):

    tf_repo = f'{provision_root}/{resource_type}/{runtime_env}'

    t = WrapTerraform(tf_path=tf_repo)

    if just_state:

        t.configure_terraform(tree, new_state=False)

        if action == WieldAction.APPLY:
            t.cmd(terraform_action=TerraformAction.INIT)

        terraform_action = wield_to_terraform(action)

        t.cmd(terraform_action=terraform_action)
    else:
        logging.debug("skipping terraform actions and just fetching state")

    state = t.state()

    return state


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    _conf = get_conf("mac")

    _tree = _conf['dataproc_terraform']

    _tf_dir = _conf['namespaces_dir']

    os.makedirs(_tf_dir, exist_ok=True)

    _t = WrapTerraform(tf_path=_tf_dir)
    _t.configure_terraform(_tree, True)

    #
    #
    # r = t.cmd()
    #
    # logging.debug('foo')
