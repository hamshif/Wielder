#!/usr/bin/env python
import json
import logging
import os
import random

from wielder.util.commander import subprocess_cmd as _cmd, subprocess_cmd
from wielder.util.log_util import setup_logging
from wielder.util.templater import config_to_terraform
from wielder.util.credential_helper import get_aws_mfa_cred_command
from wielder.util.util import DirContext
from wielder.wield.enumerator import TerraformAction, TerraformReplyType, CredType, WieldAction, wield_to_terraform


class WrapTerraform:

    def __init__(self, root_path, run_dir, conf):
        """
        Wraps terraform commands in context (directory, credentials ....),
        Its tightly coupled with hocon configuration tree
        This is a work in progress, use with caution in complex situations
        :param root_path: The path to the terraform root
        :type root_path: str
        :param conf config tree
        :type conf: hocon config
        """

        self.root_path = root_path
        self.run_dir = run_dir
        self.run_path = f'{root_path}/{run_dir}'
        self.conf = conf

        self.backend_root = conf.backend_root
        self.backend_name = conf.backend_name
        self.backend_tree = conf.backend
        self.tfvars = conf.tfvars

        self.verbose = conf.verbose

        cred_type = None

        try:
            cred_type = CredType(conf.cred_type)
            self.cred_role = conf.cred_role
        except Exception as e:
            logging.warning(f"{e}\nno CLI credential type is being used")

        self.cred_type = cred_type

    def run_cmd_in_repo(self, t_cmd, get_reply, reply_type):

        with DirContext(self.run_path):

            if self.cred_type == CredType.AWS_MFA:
                cmd_prefix = get_aws_mfa_cred_command(self.cred_role)
                t_cmd = f'{cmd_prefix} {t_cmd}'

            logging.info(f"Running:\n{t_cmd}\nin: {self.run_path}\n")

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
                t_cmd = f'{t_cmd} -upgrade -backend-config "{self.backend_root}/{self.backend_name}.tf" -force-copy'

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
            full = f'{self.run_path}/terraform.tfstate'
            _cmd(f"mv {full} {full}.{r}.copy")

        config_to_terraform(
            tree=self.tfvars,
            destination=self.run_path,
            print_vars=True
        )

        if self.backend_tree is not None and self.backend_name is not None:
            backend_full_path = f'{self.root_path}/backends_tf'

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

    # TODO remove these ugly AWS specific actions (Inherit Terraformer with AWSTerraformer & create factory method)
    def actions_for_eks_destroy(self):

        logging.info("In preparation for destroying EKS destroying some auth resources")

        tf_cmd = "terraform state rm 'module.eks[0].kubernetes_config_map.aws_auth'"
        logging.info(f'running terraform command:\n{tf_cmd}')
        self.run_cmd_in_repo(t_cmd=tf_cmd, get_reply=False, reply_type=TerraformReplyType.TEXT)

        tf_cmd = "terraform state rm 'module.eks[0].kubernetes_config_map_v1_data.aws_auth'"
        logging.info(f'running terraform command:\n{tf_cmd}')
        self.run_cmd_in_repo(t_cmd=tf_cmd, get_reply=False, reply_type=TerraformReplyType.TEXT)

    def wield_protocol(self, action):

        self.configure_tfvars(new_state=False)

        if self.conf.init:
            self.terraform_cmd(terraform_action=TerraformAction.INIT)

        partial_modules = None
        if self.conf.partial:
            partial_modules = self.conf.partial_modules

        if action == TerraformAction.APPLY and 'create_eks' in self.conf.tfvars and not self.conf.tfvars.create_eks:

            self.actions_for_eks_destroy()

        self.terraform_cmd(terraform_action=action, apply_targets=partial_modules)

        logging.info('finished deploying Terraform resources')

        out = self.read_output()
        logging.info(out)

        return out

    def destroy_protocol(self):

        destroy_protocol = self.conf.destroy_protocol

        if 'destroy_eks' in destroy_protocol and destroy_protocol.destroy_eks:

            self.actions_for_eks_destroy()

        self.configure_tfvars(new_state=False)
        self.terraform_cmd(terraform_action=TerraformAction.INIT)
        self.terraform_cmd(terraform_action=TerraformAction.REFRESH)
        terraform_action = wield_to_terraform(WieldAction.DELETE)

        partial_modules = None
        if destroy_protocol.partial:
            partial_modules = destroy_protocol.partial_modules

        # TODO parse and react to reply
        terraform_reply = self.terraform_cmd(terraform_action=terraform_action, apply_targets=partial_modules)

        out = self.read_output()
        logging.info(out)
        logging.info('finished destroying Terraform resources.')

        if 'destroy_eks' in destroy_protocol and destroy_protocol.destroy_eks:

            context_cmd = f'kubectl config use-context {destroy_protocol.kube_context}'
            logging.info(f'running: {context_cmd}')
            os.system(context_cmd)

        return out


if __name__ == "__main__":
    setup_logging(log_level=logging.DEBUG)


