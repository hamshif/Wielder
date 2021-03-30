#!/usr/bin/env python
import json
import logging
import os
import random

from wielder.util.commander import subprocess_cmd as _cmd, subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.util.templater import config_to_terraform
from wielder.util.terraform_credential_helper import get_aws_mfa_cred_command
from wielder.util.util import DirContext
from wielder.wield.enumerator import TerraformAction, TerraformReplyType, CredType


class WrapTerraform:

    def __init__(self, repo_path, conf):
        """
        Wraps terraform commands in context (directory, credentials ....),
        Its tightly coupled with hocon configuration tree
        This is a work in progress, use with caution in complex situations
        :param repo_path: The path to the terraform root
        :type repo_path: str
        :param conf config tree
        :type conf: hocon config
        """
        self.repo_path = repo_path
        self.conf = conf

        self.backend_name = conf.backend_name
        self.backend_tree = conf.backend
        self.tfvars = conf.tfvars

        self.verbose = conf.verbose

        cred_type = None

        try:
            cred_type = CredType(conf.cred_type)
        except Exception as e:
            logging.warning(f"{e}\nno CLI credential type is being used")

        self.cred_type = cred_type

    def run_cmd_in_repo(self, t_cmd, get_reply, reply_type):

        with DirContext(self.repo_path):

            if self.cred_type == CredType.AWS_MFA:
                cmd_prefix = get_aws_mfa_cred_command()
                t_cmd = f'{cmd_prefix} {t_cmd}'

            logging.info(f"Running:\n{t_cmd}\nin: {self.repo_path}\n")

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
                logging.info("Not sending reply, note that terraform can take some time to respond")
                os.system(t_cmd)
                return 'Command run and finished without collecting reply'

    # TODO this is quick and dirty, create access functions in the SDK to better wrap Terraform
    def terraform_cmd(self, terraform_action=TerraformAction.PLAN, auto_approve=True, apply_targets=None):
        """
        This is in development and not thoroughly tested!!!
        :param apply_targets: List of modules to target in apply
        :param terraform_action: Basic Terraform command
        :param auto_approve: For destroy and apply auto approval
        :return: terraform CLI output if applicable
        """

        get_reply = False
        reply_type = TerraformReplyType.TEXT

        t_cmd = f'terraform {terraform_action.value}'

        if terraform_action == TerraformAction.SHOW:

            get_reply = True
            reply_type = TerraformReplyType.JSON

        elif terraform_action == TerraformAction.INIT:

            if self.backend_name is not None:
                t_cmd = f'{t_cmd} -backend-config "backend/{self.backend_name}.tf" -force-copy'

        elif terraform_action == TerraformAction.APPLY:

            if apply_targets is not None:

                for module in apply_targets:

                    t_cmd += f' --target=module.{module}'

            if auto_approve:
                t_cmd = f'{t_cmd} -auto-approve'

        elif terraform_action == TerraformAction.DESTROY:

            if auto_approve:
                t_cmd = f'{t_cmd} -auto-approve'

            if self.conf.destroy_protocol.partial:

                for module in self.conf.destroy_protocol.partial_modules:

                    t_cmd += f' --target=module.{module}'

            t_cmd = f'{t_cmd} -refresh=true'

        if terraform_action == TerraformAction.APPLY:
            t_cmd = f'{t_cmd} -parallelism={self.conf.parallelism}'

        reply = self.run_cmd_in_repo(
            t_cmd=t_cmd,
            get_reply=get_reply,
            reply_type=reply_type
        )

        if get_reply:
            return reply

    def configure_tfvars(self, new_state=False):
        """
        Converts a Hocon configuration to Terraform in the path
        :param new_state:
        :type new_state: bool
        :return:
        :rtype:
        """

        if new_state:
            logging.debug("Trying to remove local terraform state files if they exist")
            r = random.randint(3, 10000)
            full = f'{self.repo_path}/terraform.tfstate'
            _cmd(f"mv {full} {full}.{r}.copy")

        config_to_terraform(
            tree=self.tfvars,
            destination=self.repo_path,
            print_vars=True
        )

        if self.backend_tree is not None and self.backend_name is not None:
            backend_full_path = f'{self.repo_path}/backend/'

            config_to_terraform(
                tree=self.backend_tree,
                destination=backend_full_path,
                name=f'{self.backend_name}.tf',
                print_vars=True
            )

    def read_output(self):

        t_cmd = 'terraform output -json'

        output = self.run_cmd_in_repo(t_cmd, True, TerraformReplyType.JSON)

        return output


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
