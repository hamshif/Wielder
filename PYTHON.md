
Python
=

Virtual Environment
-
pyenv virtualenvs 
https://github.com/pyenv/pyenv-virtualenv
```
brew install pyenv
pyenv install 3.6.5 / 3.7.5 not tested with airflow / 3.8.0 (problems with hocon parsing)
brew install pyenv-virtualenv pyenv-virtualenvwrapper
```
To config add these lines in .zshrc or .bashrc
```
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Create virtualenv
```
pyenv virtualenv 3.7.5 wielder
pyenv activate wielder 
```

dependencies while in virtualenv active shell
```
pip install --upgrade pip

pip install gitpython rx Cython pyhocon flask confluent-kafka kafka-python Kazoo cassandra-driver kubernetes kafka

pip install apache-airflow
```

you can Either use wielder locally with .package_by_bash.sh script or pip install wielder


To delete 
```
pyenv virtualenv-delete <name>
```

while wielder virtualenv is active run package_py.bash files in
1. Wielder
1. wield-services
1. data-common
 

from virtualenv context in any shell call any project script (right click -> copy path)  
to see help add -h 

 
For IDE support
-
 1. Locate interpreter in shell with virtual env ```which python```
 1. copy path
 1. 
 + Intellij:
  1. Right Click Module (In project panel) >> 
  1. open module settings >> 
  1. module 
  1. Python 
  1. [+] to add sdk
  1. [...] to configure path
  1. paste copied python path path
  1. apply / ok ...
  1. wait a bit for intellij to process.
 
 PyPI
 =
 
https://packaging.python.org/tutorials/packaging-projects/
https://widdowquinn.github.io/coding/update-pypi-package/

remove old uploads in dist folder if they exist

Make sure you have pypirc by logging into pypi project and getting a token
Or use name and password from PyPi login
```
cd <path to>/Wielder

pyenv activate wielder
python -m pip install --upgrade twine
pip install --upgrade setuptools wheel twine

python setup.py sdist bdist_wheel

twine upload -r pypi dist/*
```