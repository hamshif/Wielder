import os


class WieldPacker:
    """
    A class for wrapping build and image packing information and functionality
    """

    def __init__(self, conf):

        app = conf.app
        app_conf = conf[app]

        self.app = app
        self.origin_path = app_conf.code_root
        self.wielder_commit = conf.wielder_commit
        self.origin_commit = app_conf.code_repo_commit
        self.plan = app_conf.cicd.pack
        self.build_conf = app_conf.build_instructions

        pack_dir = f'{conf.packing_root}/{conf.unique_name}/{app_conf.code_repo_name}'
        os.makedirs(pack_dir, exist_ok=True)

        self.pack_dir = pack_dir
        self.build_dir = f'{pack_dir}/{app_conf.build_dir}'
        self.artifacts_dir = f'{self.pack_dir}/image_artifacts'

        print(f'pack plan:\n{self.plan}')

