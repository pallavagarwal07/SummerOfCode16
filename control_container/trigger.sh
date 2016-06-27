#!/usr/bin/env bash
$docker run -v "${cachePath}/portage":/usr/portage \
    -v "${cachePath}/build":/root/build \
    -it pallavagarwal07/gentoo-stabilization:split /root/container.py $1
