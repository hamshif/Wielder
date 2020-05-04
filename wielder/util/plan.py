#!/usr/bin/env python
import logging

from wielder.util.arguer import get_kube_parser, process_args
from wielder.util.templater import remove_non_templates, gather_templates, templates_to_instances

if __name__ == "__main__":

    kube_parser = get_kube_parser()
    kube_args = kube_parser.parse_args()

    conf = process_args(kube_args)
    conf.attr_list(True)

    where = "/Users/gbar/stam/rtp/RtpKube/deploy/"

    remove_non_templates(where, conf)

    templates = gather_templates(where, conf)

    logging.info(f"templates:\n{templates}")
    templates_to_instances(templates, conf.template_variables)


