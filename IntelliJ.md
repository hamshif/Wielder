This module can be placed in the same Intellij project with other modules
such as
https://github.com/hamshif/data-common.git \
https://github.com/hamshif/dags.git

## To open it with IntelliJ
###Plugins:

1. Python
2. Markdown      
3. Jenv
4. Scala
5. .ignore
6. Bash
7. Terraform
5. hocon
6. Maven
7. Perl

open ~/dev with atom
copy and modify all the .imld files to iml (Intellij reads them)
make sure the penv name is correct


###Init workspace
1. Open project in super projectr directory
2. Add multiple SDKs :
    - Java 1.8
    - Java 11
    - Python Wielder pyenv.

The SDK paths in JEnv look like this - **/Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home**\
Add SDK pointing to python interpreter -
`For downloading SDK from IntelliJ IDEA go to File -> Project Structure... -> SDKs -> '+' -> Download JDK chose version and download`


Open project with atom and copy all .imld files into .iml and make sure the pyenv is correct etc...


###Open workspace
1. open project structure
2. remove any module if it was created automatically (File -> Project Structure... -> Modules -> '-')

###Python modules:
1. Add Wielder module (File -> New -> Module from existing sourse -> select folder Wielder (~/duds/Wielder))
    - If module wasn't add to the project try **File -> New -> Module... -> Select SDK -> Next -> Select folder -> (if it ask override click Yes) -> Finish**
2. Add pep-services module in the same way as Wielder module(step 1)
3. To get intellisense add module src dirs to SDK classpath thus:
   - **File >> project structure >> SDKs >> class path tab >> + >> ..../pep-services/src  or mark src dir as source for intellisense with right click on project (right click -> Mark directory as -> Sources Root)**
4. Add dependencies for pep-services to **Wielder File -> Project Structure... -> Modules -> choise pep-services -> tab dependencies -> '+' ->  Module dependency -> select Wielder**

###Maven modules:
Maven modules e.g. pipelines add a module using maven (there is some fine-tuning because the project structure is nested modules)
1. File -> new -> module from existing source -> maven -> next
you might have to add Scala directories as source
1. Add non framework directories e.g. docker scripts from existing sources
1. Add Python frameworks using preprepared virtualenvwrapper




If you want to change the resulting default dir structure change from project view to Project Files
