FROM gentoo/stage3-amd64
ADD *.py *.sh /root/
ADD gentoo.conf /etc/portage/repos.conf/
RUN mkdir -p /root/build; \
    emerge --sync; \
    eselect python set python2.7; \
    echo 'MAKEOPTS="-j4"' >> /etc/portage/make.conf; \
    USE="-*" emerge sci-mathematics/minisat \
                    dev-python/requests \
                    dev-python/numpy \
                    dev-vcs/git \
                    app-portage/eix \
                    app-portage/portage-utils; \
    easy_install satispy; \
    easy_install pycosat; \
    rm -rf /usr/portage;
CMD ["/root/logger.sh"]
