
Python
=

create virtualenv
-
 ```
 brew install python3
 pip3 install virtualenv virtualenvwrapper
 mkvirtualenv -p $(which python3) kube3
 ```
dependencies
-
 ```
 cd RtpKube
 echo "export PYTHONPATH=$(PYTHONPATH):$(pwd)" >> ~/.bashrc
 source ~/.bashrc
 ```

 ```
 workon kube3
 pip install kubernetes flask rx
 ```
or Use requirements.txt in rxkube dir to fill the environment:
 
 ```
 workon kube3
 pip install -r requirements.txt --no-index --find-links file:///tmp/packages
 ```

 
use virtualenv in any shell
-
 ```
 workon kube3
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