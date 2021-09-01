#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"

pyenv_name=$1

if [ -z "$pyenv_name" ]
then
      echo "\$pyenv_name is empty"
      pyenv_name=wield
else
      echo "\$pyenv_name is NOT empty"
fi

echo "Using or creating $pyenv_name pyenv"

python -V

eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv deactivate

existing_envs=$(pyenv virtualenvs)

if [[ "$existing_envs" == *"$pyenv_name"* ]]; then
    echo "$pyenv_name virtualenv exists."
else

#    pyenv install 3.7.5
    echo "$pyenv_name virtualenv doesn't exist.";
    pyenv virtualenv 3.7.5 $pyenv_name

fi

pyenv activate $pyenv_name

python -V

pip install --upgrade pip

echo 'installing wielder'
pip install -e ../../


echo 'floobatzky'
