# Copyright 1999-2016 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Id$

EAPI=6

DESCRIPTION="Client Side stabilization of Gentoo Packages"
SRC_URI="https://github.com/pallavagarwal07/SummerOfCode16/archive/${PVR}.tar.gz -> ${P}.tar.gz"

LICENSE="GPL-3"
SLOT="0"
KEYWORDS="amd64"
IUSE=""

DEPEND="app-emulation/docker"
RDEPEND="$DEPEND"

src_unpack() {
	unpack ${A}
	mv * "${S}"
}

src_install() {
	newbin Containers/scripts/ControlContainer/wrapper.sh orca_ci
}
