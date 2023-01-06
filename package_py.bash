#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"


echo 'pyenv activate wielder if using locally'
pip install -e ./

# TODO use the next version published to pip supporting up to Python 3.11
git clone https://github.com/datastax/python-driver.git

pip install -e ./python-driver