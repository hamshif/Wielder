#!/usr/bin/env python

import argparse
import sys
import os
from culture_astronomy.core.utils import get_app_conf # Using astronomy utils as proxy for config resolution
from wielder.wield.wgit_dag import WGitDag

def main():
    parser = argparse.ArgumentParser(description="Wielder Agentic Git CLI (wield-git)")
    subparsers = parser.add_subparsers(dest="command", help="Agentic DAG Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Init a new feature journey")
    init_parser.add_argument("--name", required=True, help="Feature name")
    init_parser.add_argument("--type", default="feature", help="Journey type (feature/bug/etc)")

    # save
    save_parser = subparsers.add_parser("save", help="Save commit with semantic seal")
    save_parser.add_argument("message", help="User commit message")

    # switch
    switch_parser = subparsers.add_parser("switch", help="Switch feature node")
    switch_parser.add_argument("--node", required=True, help="Target node name (e.g. client, api)")

    args = parser.parse_args()

    # Load config (Standard Wielder resolution)
    # Note: In a true universal CLI, we'd have a way to resolve this without a specific domain proxy
    conf = get_app_conf(app='ingest_astronomy')
    dag = WGitDag(conf)

    if args.command == "init":
        dag.init_feature(args.name, args.type)
    elif args.command == "save":
        dag.save_commit(args.message)
    elif args.command == "switch":
        dag.switch_node(args.node)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
