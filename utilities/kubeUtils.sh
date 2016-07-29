#!/usr/bin/env bash
#Easy utilities and mappings for debugging with kubernetes
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}"  )" && pwd  )"
REPO="$( cd "$DIR/../" && pwd )"

alias cr="kubectl create -f $REPO/Containers/Orca-Deployment.yml"
alias de="kubectl delete -f $REPO/Containers/Orca-Deployment.yml"
alias cdr="cd $REPO"
alias cdc="cd $REPO/Containers"
alias cds="cd $REPO/Containers/scripts"
alias bse="docker build -f $REPO/Containers/Dockerfile-Server \
    -t pallavagarwal07/gentoo-stabilization:server $REPO/Containers/"
alias bso="docker build -f $REPO/Containers/Dockerfile-Solver \
    -t pallavagarwal07/gentoo-stabilization:solver $REPO/Containers/"
alias bcl="docker build -f $REPO/Containers/Dockerfile-Client \
    -t pallavagarwal07/gentoo-stabilization:client $REPO/Containers/"
alias pse="docker push pallavagarwal07/gentoo-stabilization:server"
alias pso="docker push pallavagarwal07/gentoo-stabilization:solver"
alias pcl="docker push pallavagarwal07/gentoo-stabilization:client"

gp() {
    all=$(kubectl get pods | tail -n +2)
    term=$(echo "$all" | grep 'Terminating')
    started=$(comm -23 <(echo "$all") <(echo "$term"))
    echo "$started"
}

lse() {
    all=$(kubectl get pods | tail -n +2)
    term=$(echo "$all" | grep 'Terminating')
    started=$(comm -23 <(echo "$all") <(echo "$term"))
    serverName=$( echo "$started" | grep -i server | grep -oP '^[^ ]*' )
    kubectl logs -f $serverName
}

lde() {
    all=$(kubectl get pods | tail -n +2)
    term=$(echo "$all" | grep 'Terminating')
    started=$(comm -23 <(echo "$all") <(echo "$term"))
    Name=$( echo "$started" | grep -i dep- | grep -oP '^[^ ]*' )
    kubectl logs -f $Name
}

lfl() {
    all=$(kubectl get pods | tail -n +2)
    term=$(echo "$all" | grep 'Terminating')
    started=$(comm -23 <(echo "$all") <(echo "$term"))
    Name=$( echo "$started" | grep -i flag | grep -oP '^[^ ]*' )
    kubectl logs -f $Name
}

ldb() {
    all=$(kubectl get pods | tail -n +2)
    term=$(echo "$all" | grep 'Terminating')
    started=$(comm -23 <(echo "$all") <(echo "$term"))
    Name=$( echo "$started" | grep -i "db-" | grep -oP '^[^ ]*' )
    kubectl logs -f $Name
}
