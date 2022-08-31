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
   echo 'export PATH="/usr/local/opt/ncurses/bin:$PATH"' >> ~/.zshrc
   echo 'export LDFLAGS="-L/usr/local/opt/ncurses/lib"' >> ~/.zshrc
   echo 'export CPPFLAGS="-I/usr/local/opt/ncurses/include"' >> ~/.zshrc

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

brew install --cask iterm2

brew install --cask atom

if [[ $(command -v which pyenv) == "which" ]]; then
  brew install pyenv -vd
  echo 'export PATH="/usr/local/opt/openssl@1.1/bin:$PATH"' >> ~/.zshrc
  echo 'export LDFLAGS="-L/usr/local/opt/openssl@1.1/lib"' >> ~/.zshrc
  echo 'export CPPFLAGS="-I/usr/local/opt/openssl@1.1/include"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.zshrc

else
   echo "pyenv already installed"
   which pyenv
fi

softwareupdate --install-rosetta

if [[ $(command -v which jenv) == "which" ]]; then

  brew install jenv
  echo 'export PATH="$HOME/.jenv/bin:$PATH"' >> ~/.zshrc
  echo 'eval "$(jenv init -)"' >> ~/.zshrc

  brew tap AdoptOpenJDK/openjdk

  brew install adoptopenjdk11

  jenv add /Library/Java/JavaVirtualMachines/adoptopenjdk-11.jdk/Contents/Home

  jenv versions

  jenv enable-plugin maven
  jenv enable-plugin export

  jenv global 11.0

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

brew install kubectl -vd
brew install helm -vd

helm repo add stable https://charts.helm.sh/stable
helm repo add incubator https://charts.helm.sh/incubator
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts

helm repo update

brew install awscli -vd

brew install hudochenkov/sshpass/sshpass

if [[ $(command -v docker) == "" ]]; then
    echo "Installing Docker"
    brew cask install docker
    # echo "Starting docker"
    # open /Applications/Docker.app
else
    echo "Docker already installed"
    # open /Applications/Docker.app
fi


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
