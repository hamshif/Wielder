git clone https://github.com/stevieb9/berrybrew $env:userprofile/.berrybrew
powershell -noexit $env:userprofile/.berrybrew/bin\berrybrew.exe config

cpan install CPAN::Author
cpan install GD::Simple
cpan install GD::Graph
cpan install Tree::Trie
cpan install Const::Exporter
cpan install Bundle::Camelcade
cpan install Test::Block --force
cpan install Test::Kwalitee::Extra --force
cpan install Text::Colorizer
cpan install Test::Block

cpan install Try::Tiny
cpan install YAML
cpan install YAML::XS
cpan install JSON
cpan install JSON::MaybeXS
cpan install HTTP::Request
cpan install HTTP::Response
cpan install HTTP::Daemon

cpan install Data::HexDump::Range
cpan install Proc::Daemon

cpan install Pod::Coverage::TrustPod

cpan install Gzip::Faster

cpan install IO::Socket::INET6

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

cpan install DBI

#cpan install Net::SSLeay
cpan --interactive --verbose --force --notest Net::SSLeay

cpan install --force Cassandra::Client

cpan install DBD::Cassandra
#cpan install https://cpan.metacpan.org/authors/id/T/TV/TVDW/Cassandra-Client-0.16.tar.gz

cpan install Proc::ProcessTable


cpan install Term::Bash::Completion::Generator
cpan install Text::Colorizer
cpan install Data::HexDump::Range

cpan install Net::Kafka --force
cpan install Net::Kafka::Producer
cpan install Net::Kafka::Consumer

cpan install Kafka::Connection

