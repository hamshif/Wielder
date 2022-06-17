import os


class WieldPacker:
    """
    A class for wrapping build and image packing information and functionality
    """

    def __init__(self, locale, conf):

        self.origin_path = locale.code_root
        self.wielder_commit = conf.wielder_commit
        self.origin_commit = conf.code_repo_commit
        self.plan = conf.cicd.pack
        self.build_conf = conf.pack.build.build_instructions

        pack_dir = f'{locale.packing_root}/{conf.unique_name}/{locale.code_repo_name}'
        os.makedirs(pack_dir, exist_ok=True)

        self.pack_dir = pack_dir
        self.build_dir = f'{pack_dir}/{conf.build_dir}'
        self.artifacts_dir = f'{self.pack_dir}/image_artifacts'

        print(f'pack plan:\n{self.plan}')

