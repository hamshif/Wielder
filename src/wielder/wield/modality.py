

class WieldMode:
    """
    WieldMode is used for polymorphism of image packing, provisioning, deployment ...
    For example running on docker for development VS. running on GKE for quality engineering.
    """

    def __init__(self, runtime_env='docker', deploy_env='dev', debug_mode=False):
        """

        :param runtime_env: kubernetes on docker, minikube, gc, aws, azure ....
        :param deploy_env: dev, int qa, prod ...
        :param debug_mode: weather to enable remote debugging by allocating a port env variables ...
        """
        self.runtime_env = runtime_env
        self.deploy_env = deploy_env
        self.debug_mode = debug_mode
