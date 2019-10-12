Wielder
=
A reactive debuggable CI-CD automation tool
-
Reactive deployments, updates, scaling and rollbacks.
Wielder packs Git, Docker packing, Terraform, Kubernetes, ETL's & more into reactive debuggable events; 
wielding them from development through testing to production using Airflow Dags. 

* Functionality:
    * Kubernetes polymorphic plan apply (A reactive debuggable alternative to Helm declarative charts)
    * Packing code to docker containers and repositories (A reactive debuggable alternative to Jenkins, Travis ..).
    * Weaving Terraform and Kubernetes events into reactive, debuggable elastic scaling mechanisms. 
    * Automation of local development in Intellij and Kubernetes.
* Examples:
    * Waiting for Redis sentinels to find a master and come online before deploying another slave.
    * Waiting for Kafka to scale before scaling a deployment.
    * Provisioning additional cluster nodes and volumes with terraform before scaling a MongoDB stateful set.
    * Scheduled provisioning of hadoop clusters -> Running ETL's -> Deprovisioning the clusters
    * Listening to kubernetes service throughput -> provisioning infrastructure scaling -> provisioning kubernetes node scaling.
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
        * Pushes images to repository.


Use Instructions
-
To learn how to run read ../wielder/PYTHON.md