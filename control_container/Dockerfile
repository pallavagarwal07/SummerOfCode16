FROM gentoo/stage3-amd64
ADD *.py *.sh /root/
RUN mkdir -p /root/build; \
    mkdir /usr/portage; \
    emerge-webrsync; \
    eselect python set python2.7; \
    echo 'MAKEOPTS="-j4"' >> /etc/portage/make.conf; \
    USE="-*" emerge --autounmask-write \
                    sci-mathematics/minisat \
                    dev-vcs/git \
                    app-portage/eix \
                    app-portage/portage-utils; \
    yes | etc-update --automode -3; \
    USE="-*" emerge --autounmask-write \
                    sci-mathematics/minisat \
                    dev-vcs/git \
                    app-portage/eix \
                    app-portage/portage-utils; \
    easy_install satispy; \
    easy_install numpy; \
    easy_install requests; \
    easy_install pycosat; \
    rm -rf /usr/portage;
ADD gentoo.conf /etc/portage/repos.conf/
CMD ["/root/logger.sh"]
