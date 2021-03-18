#!/usr/bin/env python
import json
import logging
import os
import random

from wielder.util.commander import subprocess_cmd as _cmd, subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.util.templater import config_to_terraform
from wielder.util.terraform_credential_helper import get_aws_mfa_cred_command, CredType
from wielder.util.util import DirContext
from wielder.wield.enumerator import TerraformAction, wield_to_terraform, WieldAction


class WrapTerraform:

    def __init__(self, tf_path, backend_name=None, cred_type=None, verbose=True):
        """
        Wraps terraform command in context (directory, credentials ....),
        This is a work in progress, use with caution in complex situations
        :param tf_path: The path to the terraform root
        :type tf_path: str
        :param backend_name: Name of state if state is stored in a backend e.g. S3 bucket defaults to None.
        :type backend_name: str
        """

        self.tf_path = tf_path
        self.backend_name = backend_name
        self.cred_type = cred_type
        self.verbose = verbose

    def terraform_cmd(self, terraform_action=TerraformAction.PLAN, auto_approve=True):

        action = terraform_action.value

        with DirContext(self.tf_path):

            cmd_prefix = ''
            if self.cred_type == CredType.AWS_MFA.value:
                cmd_prefix = get_aws_mfa_cred_command()

            if terraform_action == TerraformAction.SHOW:

                t_cmd = f'{cmd_prefix}terraform show -json'

                logging.debug(f"Running:\n{t_cmd}\nThis is happening in another process so piping will be laggy!\n\n")

                state_bytes = subprocess_cmd(t_cmd, verbose=self.verbose)

                state_json = state_bytes.decode('utf8')

                try:
                    state = json.loads(state_json)

                    if self.verbose:
                        s = json.dumps(state, indent=4, sort_keys=True)
                        logging.debug(s)
                except Exception as e:
                    print(e)
                    state = json.dumps({"state": "unattainable perhaps uninitialized"})

                return state

            else:

                t_cmd = f'terraform {action}'

                if terraform_action == TerraformAction.INIT and self.backend_name is not None:
                    t_cmd = f'{t_cmd} -backend-config "backend/{self.backend_name}.tf" -force-copy'

                if auto_approve and (
                        terraform_action == TerraformAction.DESTROY or terraform_action == TerraformAction.APPLY):
                    t_cmd = f'{t_cmd} -auto-approve'

                t_cmd = f'{cmd_prefix}{t_cmd}'
                logging.debug(f"Running:\n{t_cmd}\n\n")
                os.system(t_cmd)

    def configure_terraform(self, tree, new_state=False, backend_tree=None):
        """
        Converts a Hocon configuration to Terraform in the path
        :param backend_tree: configuration for backend .tf file
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

        if backend_tree is not None and self.backend_name is not None:
            backend_full_path = f'{self.tf_path}/backend/'

            config_to_terraform(
                tree=backend_tree,
                destination=backend_full_path,
                name=f'{self.backend_name}.tf',
                print_vars=True
            )


def wield_terraform(provision_root, provision_tree, wield_action, verbose=True,
                    cred_type=None, just_view_state=False):

    init = provision_tree.init
    tfvars_tree = provision_tree.tfvrs
    backend_name = provision_tree.backend_name
    backend_tree = provision_tree.backend

    t = WrapTerraform(tf_path=provision_root, cred_type=cred_type, backend_name=backend_name, verbose=verbose)

    if not just_view_state:

        t.configure_terraform(tfvars_tree, new_state=False, backend_tree=backend_tree)

        if init:
            t.terraform_cmd(terraform_action=TerraformAction.INIT)

        terraform_action = wield_to_terraform(wield_action)

        t.terraform_cmd(terraform_action=terraform_action)

    else:
        logging.debug("skipping terraform actions and just fetching state")

    state = t.terraform_cmd(terraform_action=TerraformAction.SHOW)

    return state


if __name__ == "__main__":
    setup_logging(log_level=logging.DEBUG)

    # TODO default terraform conf to wielder
    # _conf = get_conf("mac")
    #
    # _tree = _conf['dataproc_terraform']
    #
    # _tf_dir = _conf['namespaces_dir']
    #
    # os.makedirs(_tf_dir, exist_ok=True)
    #
    # _t = WrapTerraform(tf_path=_tf_dir)
    # _t.configure_terraform(_tree, True)

    #
    #
    # r = t.cmd()
    #
    # logging.debug('foo')
