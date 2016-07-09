FROM gentoo/stage3-amd64
RUN mkdir /usr/portage; \
    emerge-webrsync; \
    eselect python set python2.7; \
    echo 'MAKEOPTS="-j4"' >> /etc/portage/make.conf; \
    USE="-*" emerge --autounmask-write \
                    sci-mathematics/minisat \
    yes | etc-update --automode -3; \
    USE="-*" emerge --autounmask-write \
                    sci-mathematics/minisat \
    easy_install satispy; \
    easy_install numpy; \
    easy_install requests; \
    easy_install pycosat; \
    rm -rf /usr/portage;
ADD . /root/
