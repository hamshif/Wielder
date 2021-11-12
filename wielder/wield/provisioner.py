import os

from wielder.util.wgit import WGit, clone_or_update


class NamespaceProvisioner:
    """
    Namespace provisioning control designed to enable concurrent terraform actions.
    We circumvent terraform one context/backend at a time by copying dir and initiating one backend per namespace
    """

    def __init__(self, locale, conf):

        self.origin_path = locale.provision_root
        self.plan = conf.terraformer

        self.repo_name = locale.provision_root.split('/')[-1]

        # wg = WGit(locale.super_project_root)
        # self.origin_commit = wg.get_submodule_commit(self.repo_name)

        wg = WGit(locale.provision_root)
        self.origin_commit = wg.commit

        provision_dir = f'{locale.wield_root}/provision/{conf.unique_name}/{self.repo_name}'
        os.makedirs(provision_dir, exist_ok=True)

        self.provision_dir = provision_dir

        clone_or_update(
            source=self.origin_path,
            destination=self.provision_dir,
            branch='dev',
            commit_sha=self.origin_commit
        )

        print(f'terraform plan:\n{self.plan}')

