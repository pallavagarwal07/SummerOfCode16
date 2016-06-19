FROM gentoo/stage3-amd64
ADD *.py /root/
ADD gentoo.conf /etc/portage/repos.conf/
ADD minisat git /bin/
RUN mkdir /usr/portage; \
    emerge --sync; \
    eselect python set python2.7; \
    echo 'MAKEOPTS="-j4"' >> /etc/portage/make.conf; \
    easy_install requests; \
    easy_install satispy; \
    easy_install pycosat; \
    touch /root/numpy.py
CMD ["python2", "/root/stabilize.py"]
