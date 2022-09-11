#!/usr/bin/env bash

xcode-select --install

# git credentials for
if [[ $(command ssh-add -l | grep  `ssh-keygen -lf ~/.ssh/id_rsa  | awk '{print $2}'`) == "" ]]; then
    echo "Adding key to  ~/.ssh/id_rsa"
    ssh-add -K ~/.ssh/id_rsa
else
    echo "Key ~/.ssh/id_rsa already exists"
fi


if [[ $(command -v brew) == "" ]]; then
    echo "Installing Homebrew"
    /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
else
    # echo "Updating Homebrew"
    # rm -rf `brew --cache`
    # mkdir `brew --cache`
     brew update -vd
    # brew cleanup -vd
    # brew doctor -vd
    echo bloop
fi


if [[ $(command -v which zsh) == "which" ]]; then
   echo "Installing zsh"
   brew install zsh
   echo 'export PATH="/opt/homebrew/opt/ncurses/bin:$PATH"' >> ~/.zshrc
   echo 'export LDFLAGS="-L/opt/homebrew/opt/ncurses/lib"' >> ~/.zshrc
   echo 'export CPPFLAGS="-I/opt/homebrew/opt/ncurses/include"' >> ~/.zshrc

   sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"

   chmod 755 /usr/local/share/zsh
   chmod 755 /usr/local/share/zsh/site-functions

else
   echo "zsh already installed"
   which zsh
fi

if [[ ! -d ~/.oh-my-zsh ]]; then
    echo "Installing oh my zsh. This will abort your script. Please re-run the script again"
    sh -c "$(curl -fsSL https://raw.github.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
else
    echo "oh-my-zsh already exists"
fi


brew install wget -vd
brew install git-lfs -vd
brew install cask openssl -vd
brew install librdkafka -vd
brew install libgd -vd
brew install libgcrypt -vd


brew install --cask iterm2 -vd

brew install --cask atom -vd

if [[ $(command -v which pyenv) == "which" ]]; then
  brew install pyenv -vd
  echo 'export PATH="/opt/homebrew/opt/openssl@1.1/bin:$PATH"' >> ~/.zshrc
  echo 'export LDFLAGS="-L/opt/homebrew/opt/openssl@1.1/lib"' >> ~/.zshrc
  echo 'export CPPFLAGS="-I/opt/homebrew/opt/openssl@1.1/include"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.zshrc

else
   echo "pyenv already installed"
   which pyenv
fi

softwareupdate --install-rosetta

if [[ $(command -v which jenv) == "which" ]]; then

  brew install jenv -vd
  echo 'export PATH="$HOME/.jenv/bin:$PATH"' >> ~/.zshrc
  echo 'eval "$(jenv init -)"' >> ~/.zshrc

  brew tap AdoptOpenJDK/openjdk -vd

  brew install adoptopenjdk11 -vd
  brew install adoptopenjdk8 -vd

  jenv add /Library/Java/JavaVirtualMachines/adoptopenjdk-11.jdk/Contents/Home
  jenv add /Library/Java/JavaVirtualMachines/adoptopenjdk-8.jdk/Contents/Home
  jenv versions
  jenv global 11.0

  jenv enable-plugin maven
  jenv enable-plugin export



  java -version
else
   echo "jenv already installed"
   which jenv
fi


if [[ $(command -v which maven) == "which" ]]; then
  brew install maven -vd

else
   echo "maven already installed"
   which maven
fi

brew install scala -vd
brew install apache-spark -vd

brew install kubectl -vd
brew install helm -vd

helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add stable https://charts.helm.sh/stable
helm repo add k8ssandra https://helm.k8ssandra.io/stable
helm repo add kminion https://raw.githubusercontent.com/cloudhut/kminion/master/charts/archives
helm repo add elastic https://helm.elastic.co

helm repo update

brew install awscli -vd

brew install hudochenkov/sshpass/sshpass -vd

if [[ $(command -v docker) == "" ]]; then
    echo "Please install Docker from dmg"

else
    echo "Docker already installed"
fi


brew install tfenv -vd
tfenv install 1.1.9
tfenv use 1.1.9
terraform -install-autocomplete



brew doctor

#
#if [[ $(command -v which gcloud) == "which" ]]; then
#    echo "Installing gcloud"
#    curl https://sdk.cloud.google.com | bash
#    ~/google-cloud-sdk/install.sh
#    gcloud auth login
#else
#    echo "gcloud already installed"
#    which gcloud
#fi
