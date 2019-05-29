This module can be placed in the same Intellij project with other modules
such as 
https://github.com/hamshif/data-common.git
https://github.com/hamshif/dags.git

To open it with IntelliJ
--

1. Download .md markdown-navigator plugin
1. Download Python plugin
1. open project in data directory
1. #TODO add multiple SDKs
1. Setup SDKs java8 Python virtualenvwrapper
1. open project structure
1.1. remove data module if it was created automatically
1.1. for maven modules e.g. pipelines add a module using maven (there is some fine tuning because the project structure is nested modules)
1. for each maven module
1.1 file -> new -> module from existing source -> maven -> next
you might have to add scala directories as source
1.1. add non framework directories e.g. docker scripts from existing sources
1.1. add Python frameworks using preprepared virtualenvwrapper


python interpreter

At project level add SDK pointing to python virtualenvwrapper (or conda, pyenv ...)
To get intellisense add module src dirs to SDK classpath  thus:
File >> project structure >> SDKs >> class path tab >> + >> ..../Wielder/src

If you want to change the resulting default dir structure change from project view to Project Files


