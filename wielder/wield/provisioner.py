import os
import wielder.util.util as wu

from wielder.util.terraformer import WrapTerraform
from wielder.util.wgit import WGit, clone_or_update
from wielder.wield.enumerator import wield_to_terraform, TerraformAction, WieldAction


class NamespaceProvisioner:
    """
    Namespace provisioning control designed to enable concurrent terraform actions.
    We circumvent terraform one context/backend at a time by copying dir and initiating one backend per namespace
    """

    def __init__(self, conf):

        self.origin_path = conf.provision_repo_url
        self.repo_name = conf.provision_repo

        self.plan = conf.terraformer

        wg = WGit(self.origin_path)
        self.origin_commit = wg.commit

        provision_dir = f'{conf.provision_root}/{conf.unique_name}/{self.repo_name}'
        wu.makedirs(provision_dir, exist_ok=True)

        self.provision_dir = provision_dir

        clone_or_update(
            source=self.origin_path,
            destination=self.provision_dir,
            commit_sha=self.origin_commit
        )

        print(f'terraform plan:\n{self.plan}')


def provision_ordered_modules(conf, wield_action, module_names, provision_root=None):

    if wield_action == WieldAction.DELETE:
        module_names.reverse()

    if provision_root is None:

        np = NamespaceProvisioner(conf)
        provision_root = np.provision_dir

    outputs = []

    for module_name in module_names:

        out = provision_module(conf, wield_action, module_name, provision_root)
        outputs.append(out)

    return outputs


def provision_module(conf, wield_action, module_name, provision_root):

    runtime_env = conf.runtime_env

    tf_dir = f'{provision_root}/{runtime_env}'

    terraform_output = None

    terraform_action = wield_to_terraform(wield_action)

    terraform_conf = conf.terraformer[module_name]

    t = WrapTerraform(root_path=tf_dir, run_dir=module_name, conf=terraform_conf)

    if terraform_action != TerraformAction.DESTROY:

        actions = conf[conf.app].cicd.actions

        if actions.provision_infrastructure or not TerraformAction.APPLY == terraform_action:

            terraform_output = t.wield_protocol(terraform_action)
    else:

        actions = conf[conf.app].cicd.destroy_actions

        if actions.destroy_infrastructure:
            terraform_output = t.destroy_protocol()

    return terraform_output

