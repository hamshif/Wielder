

class WieldMode:
    """
    WieldMode is used for polymorphism of image packing, provisioning, deployment ...
    For example running on docker for development VS. running on GKE for quality engineering.
    """

    def __init__(self, runtime_env='docker', deploy_env='dev', bootstrap_env='local'):
        """

        :param runtime_env: kubernetes on docker, minikube, gc, aws, azure ....
        :param deploy_env: dev, int qa, prod ...
        """

        runtime_env = runtime_env if runtime_env else 'docker'
        bootstrap_env = bootstrap_env if bootstrap_env else 'local'
        deploy_env = deploy_env if deploy_env else 'dev'

        self.runtime_env = runtime_env
        self.bootstrap_env = bootstrap_env
        self.deploy_env = deploy_env


class WieldServiceMode:
    """
    WieldServiceMode is used for modality of service, server, microservice module
    image packing, provisioning, deployment ...
        * Optional mounting of local code to docker for development.
        * Optional opening of debug port for remote debugging.
    """

    def __init__(self, observe=True, service_only=False, debug_mode=False,
                 local_mount=False, project_override=False):
        """
        :param observe: Option to wait for deployment to finish and log before returning
        :param service_only: Optional deploy of service without the deployment or stateful set.
               Used for pre initiating discoverable IPs when migrating dependant legacy services [monoliths, DBs].
        :param debug_mode: Optional opening of debug port for remote debugging.
               Done by allocating a port env variables ...
        :param local_mount: Optional mounting of local code to docker
               used for local development integration with IDE.
        :param project_override: Option to let project conf override module conf
        """
        self.observe = observe
        self.service_only = service_only
        self.debug_mode = debug_mode
        self.local_mount = local_mount
        self.project_override = project_override
