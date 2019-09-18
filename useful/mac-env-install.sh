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
    echo "Updating Homebrew"
    rm -rf `brew --cache`
    mkdir `brew --cache`
    brew update
    brew cleanup
    brew prune
    brew doctor
fi


#if [[ $(command -v which pip) == "which" ]]; then
#    echo "Installing pip with easy_install"
#    sudo easy_install pip
#else
#    echo "pip already installed"
#    which pip
#fi

# if you run into trouble https://stackoverflow.com/questions/13088998/homebrew-python-installing

if [[ $(command -v which python2) == "which" ]]; then
    echo "Installing python2 using brew"
    brew install python2
else
    echo "python2 already installed"
    which python2
fi


if [[ $(command -v which python3) == "which" ]]; then
    echo "Installing python3 using brew"
    brew install python3
else
    echo "python3 already installed"
    which python3
fi


if [[ $(command -v which pip3) == "which" ]]; then
    pip3 install virtualenv
    pip3 install virtualenvwrapper
else
    echo "no pip3 you need that for virtualenv and virtualenvwrapper"
fi


if [[ $(command -v docker) == "" ]]; then
    echo "Installing Docker"
    brew cask install docker
    echo "Starting docker"
    open /Applications/Docker.app
else
    echo "Docker already installed"
    open /Applications/Docker.app
fi


if [[ $(command -v mvn) == "which" ]]; then
    echo "Installing Maven"
    brew install maven
else
    echo "Maven already installed"
fi


if [[ ! -d ~/.oh-my-zsh ]]; then
    echo "Installing oh my zsh. This will abort your script. Please re-run the script again"
    sh -c "$(curl -fsSL https://raw.github.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
else
    echo "oh-my-zsh already exists"
fi

if [[ $(command -v kubectl) == "which" ]]; then
    echo "Installing Kubernetes Client"
    brew install kubectl
else
    echo "Kubernetes Client already installed"
fi


if [[ $(command -v virtualbox) == "which" ]]; then
    echo "Installing virtualbox"
    brew cask install virtualbox
else
    echo "virtualbox already installed"
    which virtualbox
fi


if [[ $(command -v which node) == "which" ]]; then
    echo "Installing node with brew"
    brew install node
else
    echo "node already installed"
    which node
fi


if [[ $(command -v which npm) == "which" ]]; then
    echo "Installing npm with brew"
    brew install npm
else
    echo "npm already installed"
    which npm
fi


if [[ $(command -v which yarn) == "which" ]]; then
    echo "Installing yarn with brew"
    brew install yarn
else
    echo "yarn already installed"
    which yarn
fi


#if [[ $(command -v which helm) == "which" ]]; then
#    echo "Installing helm with brew"
#    brew install helm
#else
#    echo "helm already installed"
#    which helm
#fi


if [[ $(command -v which gcloud) == "which" ]]; then
    echo "Installing gcloud"
    curl https://sdk.cloud.google.com | bash
    ~/google-cloud-sdk/install.sh
    gcloud auth login
else
    echo "gcloud already installed"
    which gcloud
fi



