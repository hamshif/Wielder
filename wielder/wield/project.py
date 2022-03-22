#!/usr/bin/env python
import logging
import os

from wielder.util.arguer import get_kube_parser
from wielder.util.hocon_util import object_to_conf
from wielder.wield.enumerator import local_kubes


def get_super_project_root():

    super_project_root = os.path.dirname(os.path.realpath(__file__))

    for i in range(4):
        super_project_root = super_project_root[:super_project_root.rfind('/')]

    logging.info(f'super_project_root:\n{super_project_root}')

    return super_project_root


class WielderProject:
    """
    Encapsulates project directory structure and paths
    peculiar to the machine wielder is running on.
    """

    def __init__(self, super_project_root=None, packing_root=None, provision_root=None, mock_buckets_root=None):

        if super_project_root is None:
            super_project_root = get_super_project_root()

        self.super_project_root = super_project_root

        if packing_root is None:
            packing_root = f'{super_project_root}/pack'
            os.makedirs(packing_root, exist_ok=True)

        self.packing_root = packing_root

        if provision_root is None:
            provision_root = f'{super_project_root}/provision'
            os.makedirs(provision_root, exist_ok=True)

        self.provision_root = provision_root

        if mock_buckets_root is None:
            mock_buckets_root = f'{super_project_root}/buckets'
            os.makedirs(mock_buckets_root, exist_ok=True)

        self.mock_buckets_root = mock_buckets_root

        # p = get_kube_parser()
        # ar = p.parse_known_args()[0]
        # # ar = vars(ar)
        #
        # if ar.runtime_env in local_kubes:
        #     self.buckets_root = mock_buckets_root
        # elif ar.runtime_env == 'aws':
        #     self.buckets_root = 's3://'

    def as_hocon(self):

        return object_to_conf(self)


if __name__ == "__main__":

    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    wp = WielderProject()




