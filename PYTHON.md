
Python
=

create virtualenv
-
 ```
 brew install python3
 pip3 install virtualenv virtualenvwrapper
 mkvirtualenv -p $(which python3) wielder
 ```
 in .zshrc
 
 add these lines:
 
```
  
# set where virutal environments will live
export WORKON_HOME=$HOME/.virtualenvs
# ensure all new environments are isolated from the site-packages directory
export VIRTUALENVWRAPPER_VIRTUALENV_ARGS='--no-site-packages'
# use the same directory for virtualenvs as virtualenvwrapper
export PIP_VIRTUALENV_BASE=$WORKON_HOME

# makes pip detect an active virtualenv and install to it
export PIP_RESPECT_VIRTUALENV=true
if [[ -r /usr/local/bin/virtualenvwrapper.sh ]]; then
 source /usr/local/bin/virtualenvwrapper.sh
else
 echo "WARNING: Can't find virtualenvwrapper.sh"
fi
 
VIRTUALENVWRAPPER_PYTHON=/usr/local/bin/python3
 
source /usr/local/bin/virtualenvwrapper.sh
  ```
 
dependencies
-
 ```
 cd RtpKube
 echo "export PYTHONPATH=$(PYTHONPATH):$(pwd)" >> ~/.bashrc
 source ~/.bashrc
 ```

 ```
 workon wielder
 pip install kubernetes flask rx
 ```
or Use requirements.txt in rxkube dir to fill the environment:
 
 ```
 workon wielder
 pip install -r requirements.txt --no-index --find-links file:///tmp/packages
 ```

 
use virtualenv in any shell
-
 ```
 workon wielder
 which python 
 python --version
 deactivate
 ```
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