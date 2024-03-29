#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"

v=$1

if [ -z "$v" ]
then
      echo "\$v is empty"
      v=wielder
else
      echo "\$v is NOT empty"
fi

echo "Creating or updating $v pyenv"

python -V

eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"

pyenv deactivate

existing_envs=$(pyenv virtualenvs)

echo $existing_envs

if [[ "$existing_envs" == *"$v"* ]]; then
    echo "$v virtualenv exists."
else

   pyenv install 3.10.6

    echo "$v virtualenv doesn't exist.";
    pyenv virtualenv 3.10.6 $v

fi

pyenv activate $v
echo 'pyenv activate $v'

pip install --upgrade pip
