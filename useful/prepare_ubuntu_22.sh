curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.11.1/kind-linux-amd64
chmod +x ./kind
sudo mv ./kind /usr/local/bin/

# Create kind cluster 
kind create cluster --config ./kindconfig.yaml --name kind

# Install pyenv (TODO: Add echo to `pyenv activate wielder`)
git clone https://github.com/pyenv/pyenv.git ~/.pyenv
git clone https://github.com/pyenv/pyenv-virtualenv.git ~/.pyenv/plugins/pyenv-virtualenv
#echo 'export PYENV_ROOT="$HOME/.pyenv"' >> ~/.bashrc
#echo 'export PATH="$PYENV_ROOT/bin:$PATH"' >> ~/.bashrc
#echo 'eval "$(pyenv init -)"' >> ~/.bashrc
#echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
#eval "$(cat ~/.bashrc | tail -n +10)"
pyenv install 3.8.1
pyenv virtualenv 3.8.1 wielder

# Install jenv
sudo apt install -y openjdk-11-jdk openjdk-8-jdk
git clone https://github.com/jenv/jenv.git ~/.jenv
#echo 'export PATH="$HOME/.jenv/bin:$PATH"' >> ~/.bashrc
#echo 'eval "$(jenv init -)"' >> ~/.bashrc
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
sudo mv spark-3.0.3-bin-hadoop2.7 /opt/spark
#echo "export SPARK_HOME=/opt/spark" >> ~/.bashrc
#echo "export PATH=$PATH:$SPARK_HOME/bin:$SPARK_HOME/sbin" >> ~/.bashrc
#echo "export PYSPARK_PYTHON=/usr/bin/python3" >> ~/.bashrc
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

