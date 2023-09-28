#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"

# cd Wielder/useful
# images for kind https://hub.docker.com/r/kindest/node/tags
#kube_version="v1.21.14"
kube_version="v1.25.9"

kind create cluster --config ./kindconfig.yaml --name kind --image kindest/node:$kube_version