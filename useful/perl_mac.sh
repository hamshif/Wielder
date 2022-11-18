#!/usr/bin/env bash

echo "Run this as root, it needs permissions!"

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "$0 is running from: $DIR"

# make this file's location working dir
cd "$(dirname "$0")"


    v='perl-5.30.1'

    perl_versions=$(perlbrew list)

    echo "perl_versions $perl_versions"

    if [[ "$perl_versions" == *"$v"* ]]; then
        echo "$v is installed in perlbrew."
    else
        echo "$v is not!!! installed in perlbrew.  installing ...."
        perlbrew install perl-5.30.1 --notest --force
    fi


    current_perl_version=$(which perl)

    echo "current_perl_version: $current_perl_version"

    if [[ "$current_perl_version" == *"$v"* ]]; then
        echo "$v is current version."
    else
        echo "$v is not current version."
        perlbrew switch $v
    fi

cpanm  install Const::Exporter
cpanm  install Bundle::Camelcade
cpanm  install --force Test::Block
cpanm  install Try::Tiny
cpanm  install YAML
cpanm  install YAML::XS
cpanm  install JSON
cpanm  install JSON::MaybeXS
cpanm  install HTTP::Request
cpanm  install HTTP::Response
cpanm  install HTTP::Daemon

cpanm  install GD::Simple
cpanm  install GD::Graph
cpanm  install Data::HexDump::Range
cpanm  install Proc::Daemon
cpanm  install Test::Block
cpanm  install Text::Colorizer
cpanm  install Gzip::Faster

cpanm  install IO::Socket::INET6

#export PATH="/usr/local/opt/openssl@1.1/bin:$PATH"
#export LDFLAGS="-L/usr/local/opt/openssl@1.1/lib"
#export CPPFLAGS="-I/usr/local/opt/openssl@1.1/include"

#    or add this to the .zshrc file
# Warning: Refusing to link macOS-provided software: openssl@1.1
# If you need to have openssl@1.1 first in your PATH run:
#export PATH="/usr/local/opt/openssl@1.1/bin:$PATH"
#
## For compilers to find openssl@1.1 you may need to set:
#export LDFLAGS="-L/usr/local/opt/openssl@1.1/lib"
#export CPPFLAGS="-I/usr/local/opt/openssl@1.1/include"

# For pkg-config to find openssl@1.1 you may need to set:
# export PKG_CONFIG_PATH="/usr/local/opt/openssl@1.1/lib/pkgconfig"

cpanm install DBI

#cpanm  install Net::SSLeay
OPENSSL_PREFIX=/usr/local/opt/openssl@1.1 cpanm --interactive --verbose --force Net::SSLeay


cpanm install --force Cassandra::Client

cpanm install DBD::Cassandra
#cpanm install https://cpan.metacpan.org/authors/id/T/TV/TVDW/Cassandra-Client-0.16.tar.gz

cpanm install Proc::ProcessTable

cpanm install Net::Kafka
cpanm install Net::Kafka::Producer
cpanm install Net::Kafka::Consumer

cpanm install Kafka::Connection
