#!/usr/bin/env python

import sys
import os


def add_dir_to_path(d):

    sys.path.insert(0, d)


if __name__ == "__main__":

    print(str(sys.path))

    dir_path = os.path.dirname(os.path.realpath(__file__))
    print(f"current working dir: {dir_path}")

    root_dir = dir_path.replace("/kubrx/util", '', 1)
    print(f"root dir: {root_dir}")

    add_dir_to_path(root_dir)

    # cwd = os.getcwd()
    # print(f"current working dir: {cwd}")
    #
    # current_file = sys.argv[0]
    # print(f"current file: {current_file}")