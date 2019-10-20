This module can be placed in the same Intellij project with other modules
such as 
https://github.com/hamshif/data-common.git
https://github.com/hamshif/dags.git

To open it with IntelliJ
--
Plugins:
    1. Markdown-navigator
    1. Python
    1. Jenv
    1. Scala
    1. .ignore
    1. Bash
    1. Terraform

1. open project in data directory
1. Add multiple SDKs 
   The SDK paths in JEnv look like this: /Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home
   Python at project level add SDK pointing to python interpreter
    1. Java 1.8
    1. Java 11
    1. Python Wielder virtualenv.
   
1. open project structure
1.1. remove data module if it was created automatically

Python Modules:

    1. Project >> New module from existing sources >> point to directory e.g. Wielder) >> choose Python virtualenv
    2. To get intellisense add module src dirs to SDK classpath  thus:
       File >> project structure >> SDKs >> class path tab >> + >> ..../Wielder/src 
       or mark src dir as source for intellisense with right click on project.
    3. For more intellisense in module structure add dependencies of dependent modules e.g. (in wielder-services add dependency to Wielder)

Maven modules e.g. pipelines add a module using maven (there is some fine tuning because the project structure is nested modules)
1.1 file -> new -> module from existing source -> maven -> next
you might have to add Scala directories as source
1.1. add non framework directories e.g. docker scripts from existing sources
1.1. add Python frameworks using preprepared virtualenvwrapper


If you want to change the resulting default dir structure change from project view to Project Files


