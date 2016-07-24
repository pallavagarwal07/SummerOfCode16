#!/usr/bin/env bash
pushd `dirname $0` > /dev/null
SCRIPTPATH=`pwd -P`
popd > /dev/null

useradd $PERMUSER
echo "Script is located at" $SCRIPTPATH
mkdir -p /root/build
cd /root/build

rm -rf /tmp/profiles
chown -R $PERMUSER:$PERMUSER /usr/portage
mv /usr/portage/profiles /tmp/profiles
emerge --sync 2>&1 | tee sync_logs
mv /tmp/profiles /usr/portage/profiles
emerge --info 2>&1 | tee emerge_info
eix-update
qlop    -luCv 2>&1 | tee emerge_history

python ../container.py $@

chown -R $PERMUSER:$PERMUSER /usr/portage
chown -R $PERMUSER:$PERMUSER /root/build
