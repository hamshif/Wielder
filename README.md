
Wielder
=

<h2> 
One Lib to rule them all,<br>
One Lib to find them,<br>
One Lib to bring them all<br>  
and in the darkness bind them.  
</h2>

Reactive debuggable CI-CD
-
Wielder unifies the best technologies for the job into DAG's.
Reactive deployments, canaries, updates, scaling and rollbacks.
You decide, pick and choose (fastest, cheapest, legacy...).
We do this by wrapping the technology in python and then treating it as a black-box with callbacks 

* Kubernetes? Use a polymorphic plan apply Dag (A reactive debuggable alternative to Helm declarative charts & SDK dependant Go Operators)
or alternatively use the Helm wielding module to weave charts into your process, anything to unify getting the job done.

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
    * Provisioning additional cluster nodes and volumes with terraform before scaling a Cassandra stateful set.
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

Development Instructions
=
When developing file systems side effects e.g. creating files, directories, symlinks, etc..
check if functionality exists in the util module and use it or create it there.

Development Environment & Path Handling:
-
Wielder paths simulate key-value storage commonly used in distributed environments like S3 or Google Cloud Storage. 
Distributed functionality has been battle-tested at scale on Unix-based systems and can be simulated locally to closely mirror production, optimizing development cycles, reducing bugs, minimizing DevOps overhead, and familiarizing developers with cloud and distributed environments. Initial support for Windows has also been added.

Production Environment:
-
The philosophy is to wrap everything with a consistent interface and make it DAG-compatible using tools like Airflow for high-level monitoring. If issues arise, such as a feature, bug, or operational problem, the interfacing module can be easily opened, debugged, and edited.