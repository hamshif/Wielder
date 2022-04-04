#!/usr/bin/env python
import logging

from wielder.util.log_util import setup_logging
from wielder.wield.kube_probe import is_job_complete

if __name__ == "__main__":

    setup_logging(log_level=logging.DEBUG)

    context = 'docker-desktop'
    namespace = 'wielder-services'
    res_name = 'bootcassandra'

    was_job_successful = is_job_complete(context, namespace, res_name)

    logging.info(f'was_job_successful?  the answer is .... {was_job_successful}')
