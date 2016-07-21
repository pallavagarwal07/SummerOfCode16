#!/usr/bin/env bash
pushd `dirname $0` > /dev/null
SCRIPTPATH=`pwd -P`
popd > /dev/null

mkdir -p /root/build
cd /root/build
emerge --sync > sync_logs   2> sync_errors
emerge --info > emerge_info
eix-update
qlop    -luCv > emerge_history

python ../container.py $@

find . -type d -exec chmod 777 {} \;
find . -type f -exec chmod 666 {} \;
