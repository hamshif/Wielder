#!/usr/bin/env python

__author__ = 'Gideon Bar'


class GCP:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            print("Conf items:\n______\n")
            [print(f"attribute: {k}    value: {v}") for k, v in items]

        return items


class Dataproc:

    def __init__(self):

        self.template_ignore_dirs = []

    def attr_list(self, should_print=False):

        items = self.__dict__.items()
        if should_print:

            print("Conf items:\n______\n")
            [print(f"attribute: {k}    value: {v}") for k, v in items]

        return items


def extract_gcp_to_conf(conf, gcp_services=[]):

    gcp = conf.raw_config_args['gcp']

    if 'dataproc' in gcp_services:

        dataproc = gcp['dataproc']
        conf.gcp = GCP()
        conf.gcp.dataproc = Dataproc()
        conf.gcp.dataproc.high_availability = dataproc['high_availability']

