
choco install git-lfs.install
choco install openssl
choco install kafka
choco install atom
choco install pyenv-win
choco install maven
choco install scala.install
choco install spark

python3 -m pip install notebook

python3 -m pip install spylon-kernel
python3 -m spylon_kernel install

choco install kubernetes-cli
choco install kubernetes-helm
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add stable https://charts.helm.sh/stable
helm repo add k8ssandra https://helm.k8ssandra.io/stable
helm repo add kminion https://raw.githubusercontent.com/cloudhut/kminion/master/charts/archives
helm repo add elastic https://helm.elastic.co
helm repo update

choco install awscli
choco install docker-desktop
choco install terraform

git clone https://github.com/FelixSelter/JEnv-for-Windows.git $env:userprofile/.jenv
powershell -noexit $env:userprofile/.jenv/src/jenv.ps1


#choco install libgd
#choco install libgcrypt
