Wielder
=
Reactive debuggable CI-CD
-

Kubernetes polymorphic plan apply (A reactive debuggable alternative to Helm declarative charts)

Reactive deployments, canaries, updates, scaling and rollbacks.

Wielder wields Git, Docker, Terraform, Kubernetes, Airflow, ETLs & more into reactive debuggable event sequences; 
to guide code from development through testing to production. 

* Functionality:
    * Kubernetes polymorphic plan apply (A reactive debuggable alternative to Helm declarative charts)
    * Packing code to docker containers and repositories (A reactive debuggable alternative to Jenkins, Travis etc..).
    * Weaving Terraform and Kubernetes events into reactive, debuggable elastic scaling mechanisms. 
    * Automation of local development in Intellij and Kubernetes.
    * One stop shop for CLI and configuration, using Hocon a superset of JSON, YAML integration with Terraform.
* Examples:
    * Waiting for Zookeeper to come online before deploying or scaling Kafka nodes.
    * Waiting for Redis sentinels to find a master and come online before deploying another slave.
    * Provisioning additional cluster nodes and volumes with terraform before scaling a MongoDB stateful set.
    * Scheduled provisioning of hadoop clusters -> Running ETL's -> Deprovisioning the clusters
    * Listening to Kubernetes service throughput -> provisioning infrastructure scaling with terraform -> provisioning kubernetes node scaling.
    * Use of the same infrastructure as code to develop locally and on deploy to the cloud.


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
        * Pushing images to repository.


Use Instructions
-
To learn how to run read PYTHON.md