FROM pallavagarwal07/gentoo-minimal:latest
ADD *.py /root/
ADD gentoo.conf /etc/portage/repos.conf/
ADD minisat git /bin/
RUN mkdir /usr/portage; \
    emerge --sync; \
    eselect python set python2.7; \
    easy_install requests; \
    easy_install satispy; \
    easy_install pycosat;
