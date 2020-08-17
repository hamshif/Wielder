
Python
=

Virtual Environment
-
pyenv virtualenvs 
https://github.com/pyenv/pyenv-virtualenv
```
brew install pyenv
pyenv install 3.6.5
brew install pyenv-virtualenv pyenv-virtualenvwrapper
```
To config add these lines in .zshrc or .bashrc
```
eval "$(pyenv init -)"
eval "$(pyenv virtualenv-init -)"
```

Create virtualenv
```
pyenv virtualenv 3.8.0 wielder
pyenv activate wielder 
```

dependencies while in virtualenv active shell
```
pip install --upgrade pip 
pip install gitpython rx Cython pyhocon flask confluent-kafka kafka-python Kazoo cassandra-driver kubernetes apache-airflow 

```

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
  



TODO Automate

If you want confluent kafka
```
brew install librdkafka
pyenv activate wielder
pip install confluent-kafka
```

```
pyenv virtualenv 3.7.4 test
pyenv activate  test
pip install --upgrade pip
pip install Cython

pip install 'apache-airflow[mysql]'
pip install 'apache-airflow[all]'
```