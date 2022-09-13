#!/bin/bash


docker pull docker.io/bitnami/zookeeper:3.7.0-debian-10-r106
docker pull quay.io/cloudhut/kminion:v2.2.0

docker pull docker.io/bitnami/kafka-exporter:1.3.1-debian-10-r64
docker pull docker.io/bitnami/kubectl:1.23.4-debian-10-r17
docker pull docker.io/bitnami/kafka:3.1.0-debian-10-r40
docker pull docker.io/bitnami/jmx-exporter:0.16.1-debian-10-r17

docker pull docker.io/thelastpickle/cassandra-reaper:3.1.1
docker pull docker.io/k8ssandra/reaper-operator:v0.3.5
docker pull docker.io/k8ssandra/cass-operator:v1.10.3
docker pull k8ssandra/cass-management-api:4.0.1-v0.1.37
docker pull docker.io/datastax/cass-config-builder:1.0.4
docker pull docker.io/busybox:1.35.0
docker pull docker.io/k8ssandra/system-logger:6c64f9c4

docker pull quay.io/prometheus/prometheus:v2.36.1                                                                      c70a5daad275   3 months ago        206MB
docker pull quay.io/prometheus-operator/prometheus-config-reloader:v0.57.0                                                                      bc9b4082034e   3 months ago        12.2MB
docker pull quay.io/prometheus-operator/prometheus-operator:v0.57.0                                                                      0a51339a8b4a   3 months ago        51.6MB
docker pull quay.io/prometheus/alertmanager:v0.24.0                                                                      913727cc7dd5   5 months ago        59.8MB
docker pull quay.io/prometheus/node-exporter:v1.3.1