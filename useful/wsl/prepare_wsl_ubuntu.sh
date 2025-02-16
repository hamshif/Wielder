#!/usr/bin/env bash

sudo apt update -y && sudo apt upgrade -y

# Git Large File Storage
sudo apt install -y git-lfs

# OpenSSL
sudo apt install -y openssl

# librdkafka
sudo apt install -y librdkafka-dev

# Zsh
sudo apt install -y zsh

# Wget
sudo apt install -y wget

# OpenJDK 11 and 8
sudo apt install -y openjdk-11-jdk openjdk-8-jdk

# Maven
sudo apt install -y maven

# Scala
sudo apt install -y scala

# Kubectl
sudo apt install -y kubectl

# Helm
sudo apt install -y helm

# AWS CLI
sudo apt install -y awscli


# git credentials for
if [[ $(command ssh-add -l | grep  `ssh-keygen -lf ~/.ssh/id_rsa  | awk '{print $2}'`) == "" ]]; then
    echo "Adding key to  ~/.ssh/id_rsa"
    ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
    # Follow the prompts to save the key (usually in ~/.ssh/id_rsa)

else
    echo "Key ~/.ssh/id_rsa already exists"
fi


curl https://pyenv.run | bash

# Add pyenv to bash so that it loads automatically
echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.zshrc
echo 'eval "$(pyenv init --path)"' >> ~/.zshrc
echo 'eval "$(pyenv init -)"' >> ~/.zshrc

# Restart shell
exec "$SHELL"

pyenv install 3.10
pyenv virtualenv 3.10 wielder

# Install jenv

git clone https://github.com/jenv/jenv.git ~/.jenv
#echo 'export PATH="$HOME/.jenv/bin:$PATH"' >> ~/.zshrc
#echo 'eval "$(jenv init -)"' >> ~/.zshrc
eval "$(cat ~/.zshrc | tail -n +10)"
jenv enable-plugin export
eval "$(cat ~/.zshrc | tail -n +10)"
jenv add /usr/lib/jvm/java-1.8.0-openjdk-amd64/
jenv add /usr/lib/jvm/java-11-openjdk-amd64/


if [[ ! $(command -v spark-submit) == "" ]]; then

    printf "spark exists\n"

    spark-shell --version

    printf 'if you want the newest spark install with brew run:\n\n'

    printf '  brew install apache-spark -vd\n'

else

  echo 'installing spark'
  wget https://archive.apache.org/dist/spark/spark-3.3.1/spark-3.3.1-bin-hadoop3.tgz -P ~/Downloads
  mkdir -p ~/hadoop/spark-3.3.1
  tar -xvzf ~/Downloads/spark-3.3.1-bin-hadoop3.tgz -C ~/hadoop/spark-3.3.1 --strip 1
  rm -f ~/Downloads/spark-3.3.1-bin-hadoop3.tgz
  echo 'export SPARK_HOME=~/hadoop/spark-3.3.1' >> ~/.zshrc
  echo 'export PATH=$SPARK_HOME/bin:$PATH' >> ~/.zshrc
  echo 'export PYSPARK_PYTHON=/Users/$HOME/.pyenv/shims/python3' >> ~/.zshrc
  echo 'installed spark'

fi

# Install ansible via pip
#pip install ansible==2.9.6



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

kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml

echo "execute <EDITOR=nano kubectl edit deployment metrics-server -n kube-system>"
echo "add the following to the args: - --kubelet-insecure-tls"

# Enable completion
source <(kubectl completion zsh)
# Add to zshrc for persistence
echo "source <(kubectl completion zsh)" >> ~/.zshrc

# Enable completion
source <(helm completion zsh)

# Add to zshrc for persistence
echo "source <(helm completion zsh)" >> ~/.zshrc


helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add stable https://charts.helm.sh/stable
helm repo add k8ssandra https://helm.k8ssandra.io/stable
helm repo add kminion https://raw.githubusercontent.com/cloudhut/kminion/master/charts/archives
helm repo add elastic https://helm.elastic.co

helm repo update

git clone https://github.com/tfutils/tfenv.git ~/.tfenv
# Add tfenv to bash so that it loads automatically
echo 'export PATH="$HOME/.tfenv/bin:$PATH"' >>

# Restart shell
exec "$SHELL"

# Install the latest Terraform version
#tfenv install latest

# Set the latest version as the global version
#tfenv use latest

tfenv install 1.1.9
tfenv use 1.1.9
terraform -install-autocomplete

# Restart shell
exec "$SHELL"

