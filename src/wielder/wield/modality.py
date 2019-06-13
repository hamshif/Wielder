

class WieldMode:
    """
   WieldMode is used for polymorphism of image packing, provisioning, deployment ...
   For example running on docker for development VS. running on GKE for quality engineering.
   """

    def __init__(self, runtime_env='docker', deploy_env='dev'):

        self.runtime_env = runtime_env
        self.deploy_env = deploy_env

