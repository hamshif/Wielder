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
from wielder.wield.enumerator import TerraformAction, wield_to_terraform, WieldAction, TerraformReplyType


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

    def run_cmd_in_repo(self, t_cmd, get_reply, reply_type):

        with DirContext(self.tf_path):

            if self.cred_type == CredType.AWS_MFA.value:
                cmd_prefix = get_aws_mfa_cred_command()
                t_cmd = f'{cmd_prefix} {t_cmd}'

            logging.info(f"Running:\n{t_cmd}\nin: {self.tf_path}\n")

            if get_reply:
                logging.info(f"Waiting for reply, this is happening in another process and might take a lot of time.")
                state_bytes = subprocess_cmd(t_cmd, verbose=self.verbose)

                reply = state_bytes.decode('utf8')

                if state_bytes == b'\x1b[0m\x1b[0m\x1b[0m':
                    reply = json.dumps({"reply": "warning reply is empty"})
                else:

                    logging.info(f'Terraform reply:\n{reply}')

                    if reply_type is TerraformReplyType.JSON:
                        try:
                            reply = json.loads(reply)

                            if self.verbose:
                                s = json.dumps(reply, indent=4, sort_keys=True)
                                logging.debug(s)
                        except Exception as e:
                            logging.error(e)
                            reply = json.dumps({"reply": "warning couldn't get reply as json"})

                return reply

            else:
                logging.info("Not sending reply")
                os.system(t_cmd)
                return 'Command run and finished without collecting reply'

    # TODO this is quick and dirty, create access functions in the SDK to better wrap Terraform
    def terraform_cmd(self, terraform_action=TerraformAction.PLAN, sub_cmd='', auto_approve=True):
        """
        This is in development and not thoroughly tested!!!
        :param terraform_action: Basic Terraform command
        :param sub_cmd: Sub command for Terraform (currently supported only for state command)
        :param auto_approve: For destroy and apply auto approval
        :return: terraform CLI output if applicable
        """

        get_reply = False
        reply_type = TerraformReplyType.TEXT

        t_cmd = f'terraform {terraform_action.value} {sub_cmd} '

        if terraform_action == TerraformAction.STATE:
            get_reply = True

        elif terraform_action == TerraformAction.SHOW:

            get_reply = True
            reply_type = TerraformReplyType.JSON

        elif terraform_action == TerraformAction.INIT:

            if self.backend_name is not None:
                t_cmd = f'{t_cmd} -backend-config "backend/{self.backend_name}.tf" -force-copy'

        elif terraform_action == TerraformAction.DESTROY or terraform_action == TerraformAction.APPLY:

            if auto_approve:
                t_cmd = f'{t_cmd} -auto-approve'

        reply = self.run_cmd_in_repo(
            t_cmd=t_cmd,
            get_reply=get_reply,
            reply_type=reply_type
        )

        if get_reply:
            return reply

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


def run_terraform(provision_root, provision_tree, t_cmd, cred_type=None):

    logging.info(f'running terraform command:\n{t_cmd}')
    verbose = provision_tree.verbose
    backend_name = provision_tree.backend_name

    t = WrapTerraform(tf_path=provision_root, cred_type=cred_type, backend_name=backend_name, verbose=verbose)
    t.run_cmd_in_repo(t_cmd=t_cmd, get_reply=False, reply_type=TerraformReplyType.TEXT)


def wield_terraform(provision_root, provision_tree, wield_action, cred_type=None):

    verbose = provision_tree.verbose
    init = provision_tree.init
    tfvars_tree = provision_tree.tfvrs
    backend_name = provision_tree.backend_name
    backend_tree = provision_tree.backend
    view_state = provision_tree.view_state

    t = WrapTerraform(tf_path=provision_root, cred_type=cred_type, backend_name=backend_name, verbose=verbose)

    t.configure_terraform(tfvars_tree, new_state=False, backend_tree=backend_tree)

    if init:
        t.terraform_cmd(terraform_action=TerraformAction.INIT)

    terraform_action = wield_to_terraform(wield_action)

    if terraform_action is not None:
        t.terraform_cmd(terraform_action=terraform_action)

    if view_state:
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
