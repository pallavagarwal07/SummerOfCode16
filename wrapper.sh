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

normPath() {
    dr=`expand_tilde "$1"` && mkdir -p $dr && cd $dr && pwd -P
}

expand_tilde()
{
    case "$1" in
    (\~)        echo "$HOME";;
    (\~/*)      echo "$HOME/${1#\~/}";;
    (\~[^/]*/*) local user=$(eval echo ${1%%/*})
                echo "$user/${1#*/}";;
    (\~[^/]*)   eval echo ${1};;
    (*)         echo "$1";;
    esac
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

        printf "Do you want to keep a cache of downloaded packages (Y/n)? "
        read -n 1 key
        echo ""
        if [[ "$key" == "y" || "$key" == "Y" || "$key" == "" ]]; then
            config="${config}cache=1\n"
            printf "In which folder do you want to store the cache? "
            read cachePath
            if normPath "$cachePath"; then
                cachePath=`normPath "$cachePath"`
            else
                error "Path invalid or doesn't exist. Exiting."
                exit 1
            fi
            config="${config}cachePath="$cachePath"\n"
        else
            config="${config}cache=0\n"
        fi
        head -c -1 <(echo -e "$config") > "$filename"
    else
        error "This script can't run without config file. Exiting."
    fi
fi

if grep -Eqv '^#|^[^ ]*=[^\$; ]*[ 	]*$' "$filename"; then
    error "The config file is unclean. Trying to clean.."
    tmp="$(grep -E '^#|^[^ ]*=[^\$; ]*[ ]*$|^[ 	]*$' "$filename")"
    echo "$tmp" > "$filename"
fi

source "$filename"

if [ -z "$docker" ]; then
    error "Config file faulty. Docker command not found in config file."
else
    if ! command -v $docker >/dev/null 2>&1; then
        error "The executable $docker written in config - not found."
        exit 1
    fi
fi

if [ -z "$cache" ]; then
    error "Config file faulty. Cache preference not found in config file."
else
    if [[ "$cache" == "1" ]] ; then
        if [[ -z "$cachePath" ]]; then
            error "Caching on, but cache path not defined in config file."
        else
            $docker run -v "$cachePath":/usr/portage/distfiles \
                -it pallavagarwal07/gentoo-stabilization
        fi
    else
        $docker run -it pallavagarwal07/gentoo-stabilization
    fi
fi

