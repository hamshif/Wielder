#!/bin/bash
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"
# Install all necessary dependancy and libraries
sudo apt update -y

# Install all necessary dependancy 
sudo apt-get install -y make build-essential libssl-dev zlib1g-dev libbz2-dev \
libreadline-dev libsqlite3-dev wget curl llvm libncurses5-dev libncursesw5-dev \
libffi-dev liblzma-dev python-openssl git curl python3-pip apt-transport-https \
ca-certificates curl software-properties-common unzip wget git gcc bash-completion make \
gnupg g++ libgd-dev zlib1g librdkafka-dev musl-dev cpanminus

# Install perl
sudo apt install -y perl libperl-dev cpm
# Install all necessary perl libraries
export PERL_MM_USE_DEFAULT=1
cpanm install Try::Tiny YAML JSON JSON::MaybeXS
cpan JSON::MaybeXS
cpanm install HTTP::Request HTTP::Response HTTP::Daemon
cpanm install Test::Block --force
cpanm install GD::Simple GD::Graph Proc::Daemon Text::Colorizer Gzip::Faster Data::HexDump::Range
cpanm install Proc::ProcessTable
cpanm install Kafka::Connection --force
cpanm install IO::Socket IO::Socket::INET6 Net::SSLeay Cassandra::Client DBD::Cassandra DBI Const::Exporter YAML::XS Net::Kafka

# Install docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
sudo apt update
sudo apt install -y docker-ce
sudo usermod -aG docker "${USER}"

# Install helm and k8s
sudo curl https://baltocdn.com/helm/signing.asc | sudo apt-key add -
echo "deb https://baltocdn.com/helm/stable/debian/ all main" | sudo tee /etc/apt/sources.list.d/helm-stable-debian.list
sudo curl -fsSLo /usr/share/keyrings/kubernetes-archive-keyring.gpg https://packages.cloud.google.com/apt/doc/apt-key.gpg
echo "deb [signed-by=/usr/share/keyrings/kubernetes-archive-keyring.gpg] https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt-get install -y helm kubectl

# Add neccessary helm repositories
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add stable https://charts.helm.sh/stable
helm repo add k8ssandra https://helm.k8ssandra.io/stable
helm repo add kminion https://raw.githubusercontent.com/cloudhut/kminion/master/charts/archives
helm repo add elastic https://helm.elastic.co

# Install awscli
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm awscliv2.zip
rm -rf ./aws/

# Install terraform
wget https://releases.hashicorp.com/terraform/0.14.10/terraform_0.14.10_linux_amd64.zip
unzip terraform_0.14.10_linux_amd64.zip
sudo mv terraform /usr/local/bin
rm terraform_0.14.10_linux_amd64.zip

# Install kind
curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.11.1/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/

# Create kind cluster 
kind create cluster --config ./kindconfig.yaml --name kind

# Install pyenv (TODO: Add echo to `pyenv activate wielder`)
git clone https://github.com/pyenv/pyenv.git ~/.pyenv
git clone https://github.com/pyenv/pyenv-virtualenv.git ~/.pyenv/plugins/pyenv-virtualenv
echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(pyenv init -)"' >> ~/.bashrc
echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
eval "$(cat ~/.bashrc | tail -n +10)"
pyenv install 3.8.1
pyenv virtualenv 3.8.1 wielder

# Install jenv
sudo apt install -y openjdk-11-jdk openjdk-8-jdk
git clone https://github.com/jenv/jenv.git ~/.jenv
echo 'export PATH="$HOME/.jenv/bin:$PATH"' >> ~/.bashrc
echo 'eval "$(jenv init -)"' >> ~/.bashrc
eval "$(cat ~/.bashrc | tail -n +10)"
jenv enable-plugin export
eval "$(cat ~/.bashrc | tail -n +10)"
jenv add /usr/lib/jvm/java-1.8.0-openjdk-amd64/
jenv add /usr/lib/jvm/java-11-openjdk-amd64/

# Install scala
sudo apt install -y scala maven

# Install ansible via pip
pip install ansible==2.9.6

# Install Lens
wget https://api.k8slens.dev/binaries/Lens-5.3.4-latest.20220120.1.amd64.deb 
sudo dpkg -i Lens-5.3.4-latest.20220120.1.amd64.deb
sudo apt install -yf
rm Lens-5.3.4-latest.20220120.1.amd64.deb

# Install spark locally
sudo mkdir /opt/spark
sudo wget https://downloads.apache.org/spark/spark-3.0.3/spark-3.0.3-bin-hadoop2.7.tgz -P /opt
sudo mv sudo mv spark-3.0.3-bin-hadoop2.7 /opt/spark
echo "export SPARK_HOME=/opt/spark" >> ~/.bashrc
echo "export PATH=$PATH:$SPARK_HOME/bin:$SPARK_HOME/sbin" >> ~/.bashrc
echo "export PYSPARK_PYTHON=/usr/bin/python3" >> ~/.bashrc
eval "$(cat ~/.bashrc | tail -n +10)"


# Activate pyenv and install all packages
v=$1
if [ -z "$v" ]
then
      echo "\$v is empty"
      v=wielder
else
      echo "\$v is NOT empty"
fi

pyenv activate $v

../../package_py.bash

