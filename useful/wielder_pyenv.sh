#!/usr/bin/env bash



DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"

#apt-get update
#apt-get install -y librdkafka-dev

v='wielder'
existing_envs=$(pyenv virtualenvs)

if [[ "$existing_envs" == *"$v"* ]]; then
    echo "$v virtualenv exists."
else
    echo "$v virtualenv doesn't exist."
    pyenv virtualenv 3.7.5 wielder

    echo activate wielder and restart
    echo 'pyenv activate wielder'
    exit 0
fi

pip install --upgrade pip

pip install gitpython rx Cython pyhocon flask confluent-kafka kafka-python Kazoo cassandra-driver kubernetes kafka

pip install apache-airflow