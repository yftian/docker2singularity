# Created with `C:/Users/tiany/AppData/Local/Programs/Python/Python37/Lib/site-packages/docker2singularity/docker2singularity.py dockerfiles/redis`
### ubuntu:12.04 --- 2020-03-26 17:13:46.684431

### dockerfiles/redis --- 2020-03-26 17:13:46.684431
# Build redis from source
# Make sure you have the redis source code checked out in
# the same directory as this Dockerfile

FROM ubuntu:12.04
MAINTAINER dockerfiles http://dockerfiles.github.io

RUN echo "deb http://archive.ubuntu.com/ubuntu precise main universe" > /etc/apt/sources.list
RUN apt-get update
RUN apt-get upgrade -y

RUN apt-get install -y gcc make g++ build-essential libc6-dev tcl wget

RUN wget http://download.redis.io/redis-stable.tar.gz -O - | tar -xvz

# RUN tar -zvzf /redis/redis-stable.tar.gz
RUN (cd /redis-stable && make)
RUN (cd /redis-stable && make test)

RUN mkdir -p /redis-data
VOLUME ["/redis-data"]
EXPOSE 6379

ENTRYPOINT ["/redis-stable/src/redis-server"]
CMD ["--dir", "/redis-data"]

