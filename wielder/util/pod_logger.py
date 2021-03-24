#!/usr/bin/env python
import logging
import os

from wielder.util.log_util import setup_logging
from wielder.wield.deployer import get_pods


def view_logs(app_name, namespace='default'):

    pods = get_pods(name=app_name, namespace=namespace)
    pod_name = pods[0].metadata.name

    monitor_cmd = f'kubectl -n {namespace} logs -f {pod_name} '

    # print(monitor_cmd)
    logging.info(f'To monitor run:\n{monitor_cmd}')

    os.system(monitor_cmd)

    logging.info(f'To monitor run:\n{monitor_cmd}')


if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)
    view_logs('cluster-autoscaler', namespace='kube-system')
