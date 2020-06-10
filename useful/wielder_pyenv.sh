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
    pyenv virtualenv 3.8.0 wielder
fi

pip install --upgrade pip

pyenv activate wielder

pip install gitpython
pip install rx
pip install Cython
pip install kubernetes flask pyhocon Kazoo Kafka
pip install kafka-python
pip install confluent-kafka
pip install cassandra-driver

pip install apache-airflow