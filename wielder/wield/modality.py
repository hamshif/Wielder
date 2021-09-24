from wielder.util.arguer import get_kube_parser, convert_log_level


class WieldMode:
    """
    WieldMode reflects the intended distributed environment wielded.
    Used for polymorphism of CICD image packing, provisioning, deployment ...
    For example running on docker for development VS. running on GKE for production.
    """

    def __init__(self):

        kube_parser = get_kube_parser()
        kube_args = kube_parser.parse_args()

        print(kube_args)

        action = kube_args.wield
        runtime_env = kube_args.runtime_env
        deploy_env = kube_args.deploy_env
        bootstrap_env = kube_args.bootstrap_env
        unique_conf = kube_args.unique_conf
        log_level = convert_log_level(kube_args.log_level)

        self.action = action
        self.runtime_env = runtime_env
        self.bootstrap_env = bootstrap_env
        self.deploy_env = deploy_env
        self.unique_conf = unique_conf
        self.log_level = log_level


class WieldServiceMode:
    """
    WieldServiceMode is used for modality of service, server, microservice module
    image packing, provisioning, deployment ...
        * Optional mounting of local code to docker for development.
        * Optional opening of debug port for remote debugging.

    debug_mode: Optional opening of debug port for remote debugging.
    Done by allocating a port env variables ...
    local_mount: Optional mounting of local code to docker.
    used for local development integration with IDE.
    """

    def __init__(self, observe=True, service_only=False, debug_mode=False, local_mount=False, project_override=True):
        """
        :param observe: Option to wait for deployment to finish and log before returning
        :param service_only: Optional deploy of service without the deployment or stateful set.
               Used for pre initiating discoverable IPs when migrating dependant legacy services [monoliths, DBs].
        :param project_override: Option to let project conf override module conf
        """

        self.observe = observe
        self.service_only = service_only
        self.debug_mode = debug_mode
        self.local_mount = local_mount
        self.project_override = project_override


