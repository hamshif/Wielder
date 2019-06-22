

class WieldMode:
    """
    WieldMode is used for polymorphism of image packing, provisioning, deployment ...
    For example running on docker for development VS. running on GKE for quality engineering.
    """

    def __init__(self, runtime_env='docker', deploy_env='dev', debug_mode=False, local_mount=False):
        """

        :param runtime_env: kubernetes on docker, minikube, gc, aws, azure ....
        :param deploy_env: dev, int qa, prod ...
        :param debug_mode: whether to enable remote debugging by allocating a port env variables ...
        :param local_mount: whether to mount directory with code to docker. used for local development integration with IDE
        """
        self.runtime_env = runtime_env
        self.deploy_env = deploy_env
        self.debug_mode = debug_mode
        self.local_mount = local_mount
