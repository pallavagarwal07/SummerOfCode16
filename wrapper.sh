#!/usr/bin/env bash
set -e

echo ""
filename="$HOME/.gentoo-ci"

error() {
    if [ -t 2 ]; then
        echo -e "\e[1;31mError:\e[0m" $@ 1>&2
    else
        echo -e "Error:" $@ 1>&2
    fi
    echo "" 1>&2
}

warn() {
    if [ -t 2 ]; then
        echo -e "\e[1;33mImportant:\e[0m" $@
    else
        echo -e "Important:" $@
    fi
}

if [[ $EUID -eq 0 ]]; then
    error "This script should not be run using sudo or as the root user"
    exit 1
fi

if grep -w docker <(id -Gn) >/dev/null 2>&1; then
    :
else
    error "Current user is not in docker group Please add the user to docker"
    error "and retry running this script."
    exit 1
fi

if [ -e "$filename" ]; then
    :
else
    warn "No config file for gentoo-ci exists."
    printf "           Do you want to create a new one (y/n)? "
    read -n 1 key
    echo ""
    if [[ "$key" == "y"  ||  "$key" == "Y" ]]; then
        config=""

        printf "Docker command (default: docker)? "
        read -a docker
        if [[ "$docker" == "" ]];then docker=docker;else docker=${docker[0]};fi
        config="${config}docker=$docker\n"

        echo -e "${config}" > "$filename"
    else
        error "This script can't run without config file. Exiting."
    fi
fi

if grep -Eqv '^#|^[^ ]*=[^\$; ]*[ 	]*$' "$filename"; then
    error "The config file is unclean. Trying to clean.."
    tmp="$(grep -E '^#|^[^ ]*=[^\$; ]*[ ]*$' "$filename")"
    echo "$tmp" > "$filename"
fi

source "$filename"

if [ -z "$docker" ]; then
    error "Config file faulty. Docker command not found in config file."
else
    if ! command -v $docker ; then
        error "The executable $docker written in config - not found."
        exit 1
    fi
fi

$docker run -it pallavagarwal07/gentoo-stabilization
