mkdir -p /root/build
cd /root/build
emerge --sync > sync_logs   2> sync_errors
emerge --info > emerge_info
eix-update
qlop    -luCv > emerge_history

../control.py
