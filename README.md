Wielder
=

A ***reactive*** debuggable wrapper for kubernetes **declarations**



Reactive
-

* Functionality:
    * Kubernetes resource state as event streams.
    * Application state as event streams.
    * Concurrency. 
* Uses:
    * Reactive deployments, updates, scaling and rollbacks.
* Examples:
    * Waiting for redis sentinels to find a master and come online before deploying another slave.
    * Waiting for kafka to scale before scaling a deployment.
    * Provisioning additional cluster nodes and volumes with terraform before scaling a MongoDB stateful set.


Polymorphic
-

* Functionality:
    * Renders templates to kubectl yaml/json files.
    * Template variables configurable from command-line and yaml.
    * Scripted logic for deployments, updates & rollbacks.
* Uses
    * Using configuration and debuggable code to generate and deploy many architectures in many environments from a small number of templates.
* Examples:
    * Using the same yaml files to deploy on Minikube and GKE.
    * Adding config files to statefulsets.
    * Deploying canary versions.


CI-CD
-

* Functionality:
    * Facilitates creating images tailored to all environments from code base.
        * Local feature branches
        * Cloud feature branches
        * Integration
        * QE
        * Stage
        * Production
        * Pushes images to repository.


Use Instructions
-
To learn how to run read ../wielder/PYTHON.md