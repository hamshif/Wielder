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
    # brew update -vd
    # brew cleanup -vd
    # brew prune -vd
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

brew cask install iterm2


if [[ $(command -v which pyenv) == "which" ]]; then
  brew install pyenv
  echo 'export PATH="/usr/local/opt/openssl@1.1/bin:$PATH"' >> ~/.zshrc
  echo 'export LDFLAGS="-L/usr/local/opt/openssl@1.1/lib"' >> ~/.zshrc
  echo 'export CPPFLAGS="-I/usr/local/opt/openssl@1.1/include"' >> ~/.zshrc
  echo 'eval "$(pyenv init -)"' >> ~/.zshrc
  echo 'eval "$(pyenv virtualenv-init -)"' >> ~/.zshrc

else
   echo "pyenv already installed"
   which pyenv
fi

if [[ ! -d ~/.oh-my-zsh ]]; then
    echo "Installing oh my zsh. This will abort your script. Please re-run the script again"
    sh -c "$(curl -fsSL https://raw.github.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
else
    echo "oh-my-zsh already exists"
fi

brew install maven -vd
brew install kubectl -vd
brew install helm -vd
brew install awscli -vd


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
