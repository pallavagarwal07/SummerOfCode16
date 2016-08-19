#!/usr/bin/env bash
set -e
set -a

echo ""

# Default filename for the gentoo stabilization config file
filename="$HOME/.gentoo-ci"

# Print error with colors if on terminal and blankly if
# piped. Use it as `error "This is an error."`
error() {
    if [ -t 2 ]; then
        echo -e "\e[1;31mError:\e[0m" $@ 1>&2
    else
        echo -e "Error:" $@ 1>&2
    fi
    echo "" 1>&2
}

# Similar to error, use colors if on terminal and blankly
# if piped. Use it as `warn "This is a warning."`
warn() {
    if [ -t 2 ]; then
        echo -e "\e[1;33mImportant:\e[0m" $@
    else
        echo -e "Important:" $@
    fi
}


# Similar to error, use colors if on terminal and blankly
# if piped. Use it as `success "This is a warning."`
success() {
    if [ -t 2 ]; then
        echo -e "\e[1;32mSuccess:\e[0m" $@
    else
        echo -e "Success:" $@
    fi
}

# Normalize path replacing '~' with the value of $HOME
normPath() {
    dr=`expand_tilde "$1"` && mkdir -p $dr && cd $dr && pwd -P
}

# normPath uses this function to expand path containing '~'
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

# Check if the script has been run as sudo
if [[ $EUID -eq 0 ]]; then
    error "This script should not be run using sudo or as the root user"
    exit 1
fi

# Check if curent user is in docker group
if grep -w docker <(id -Gn) >/dev/null 2>&1; then
    :
else
    error "Current user is not in docker group Please add the user to docker"
    error "and retry running this script."
    exit 1
fi

# Check if the config file exists. If it doesn't, walk the user
# through the process of creating the config file with correct config
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

        key="y"
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

# Make sure that the config file has only simple assignment values.
# Anything else can cause dangerous operations and should be deleted
if grep -Eqv '^#|^[^ ]*=[^\$; ]*[ 	]*$' "$filename"; then
    error "The config file is unclean. Trying to clean.."
    tmp="$(grep -E '^#|^[^ ]*=[^\$; ]*[ ]*$|^[ 	]*$' "$filename")"
    echo "$tmp" > "$filename"
fi

# Source the config file to retrieve the configuration values
source "$filename"

# Check if the name of docker executable is known. If yes, check if the
# executable can be found in the path
if [ -z "$docker" ]; then
    error "Config file faulty. Docker command not found in config file."
else
    if ! command -v $docker >/dev/null 2>&1; then
        error "The executable $docker written in config - not found."
        exit 1
    fi
fi

# Check if preference for cache is specified in config. If yes, check
# if the corresponding folder is mentioned
if [ -z "$cache" ]; then
    error "Config file faulty. Cache preference not found in config file."
else
    if [[ -z "$cachePath" ]]; then
        error "Caching on, but cache path not defined in config file."
    else
        export PERMUSER=$USER
        rm -rf ${cachePath}/build
        mkdir -p ${cachePath}/portage ${cachePath}/build
        cd ${cachePath}/portage
        echo "Starting container to copy profiles"
        $docker pull pallavagarwal07/gentoo-stabilization:client
        $docker run --rm pallavagarwal07/gentoo-stabilization:client \
            bash -c "cd /usr/portage; tar -cf - profiles" | tar --overwrite -xf -
        echo "Starting container to build the package"
        $docker run -t -v "${cachePath}/portage":/usr/portage \
            -v "${cachePath}/build":/root/build -e PERMUSER \
            pallavagarwal07/gentoo-stabilization:client bash /root/logger.sh
    fi
fi
