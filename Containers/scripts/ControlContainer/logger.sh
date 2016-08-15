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
ret="$?"

chown -R $PERMUSER:$PERMUSER /usr/portage
chown -R $PERMUSER:$PERMUSER /root/build

cd /root/build
mv `find /var/log/portage/ -maxdepth 1 -type f` /root/build/
tar -czvf logs.tar.gz *

tempURL="$(curl http://gentoo.varstack.com:32000/temp-upload-url)"
grep '401 Unauthorized' <(curl -X PUT -T logs.tar.gz "$tempURL")

if [ $? -eq 0 ]; then
    echo "The file couldn't be uploaded because server returned 401 Unauthorized"
    exit 1000
else
    echo "Log files successfully uploaded to the server"
    exit $ret
fi
