from wielder.util.arguer import get_wielder_parser


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

    def __init__(self, debug_mode=None, local_mount=None):
        """

        :param debug_mode:
        :param local_mount:
        """

        wield_parser = get_wielder_parser()
        wield_args = wield_parser.parse_args()

        if debug_mode is None:
            debug_mode = wield_args.debug_mode

        if local_mount is None:
            local_mount = wield_args.local_mount

        self.debug_mode = debug_mode
        self.local_mount = local_mount


