#!/usr/bin/env bash



DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"


v='dud'
existing_envs=$(pyenv virtualenvs)

if [[ "$existing_envs" == *"$v"* ]]; then
    echo "$v virtualenv exists."
else

#    pyenv install 3.7.5

    echo "$v virtualenv doesn't exist."
    pyenv virtualenv 3.7.5 $v

    echo activate dud and restart
    echo 'pyenv activate $v'
    exit 0
fi

pip install --upgrade pip

pip install gitpython rx Cython pyhocon flask confluent-kafka kafka-python Kazoo cassandra-driver kubernetes kafka

pip install apache-airflow