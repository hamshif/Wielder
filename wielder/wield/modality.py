from wielder.util.arguer import get_wielder_parser, parse_known_args_strict


class WieldServiceMode:
    """
    WieldServiceMode is used for modality of service, server, microservice module
    image packing, provisioning, deployment ...
        * Optional opening of debug port for remote debugging.

    debug_mode: Optional opening of debug port for remote debugging.
    Done by allocating a port env variables ...
    """

    def __init__(self, debug_mode=None):
        """

        :param debug_mode:
        """

        wield_parser = get_wielder_parser()
        wield_args, _ = parse_known_args_strict(wield_parser)

        if debug_mode is None:
            debug_mode = wield_args.debug_mode

        self.debug_mode = debug_mode
