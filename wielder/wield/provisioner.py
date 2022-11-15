import os

from wielder.util.wgit import WGit, clone_or_update


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
        os.makedirs(provision_dir, exist_ok=True)

        self.provision_dir = provision_dir

        clone_or_update(
            source=self.origin_path,
            destination=self.provision_dir,
            commit_sha=self.origin_commit
        )

        print(f'terraform plan:\n{self.plan}')

