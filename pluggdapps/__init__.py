# -*- coding: utf-8 -*-

# This file is subject to the terms and conditions defined in
# file 'LICENSE', which is part of this source code package.
#       Copyright (c) 2011 Netscale Computing

import pkg_resources as pkg

# Import pluggdapps core
import pluggdapps.core
import pluggdapps.plugin
import pluggdapps.interfaces

from   pluggdapps.plugin import plugin_init
import pluggdapps.utils  as h

__version__ = '0.1dev'

def package() :
    """Entry point that returns a dictionary of key,value details about the
    package.
    """
    return {}

# A gotcha here !
#   The following lines executed when `pluggdapps` package is imported. As a
#   side-effect, it loops on valid pluggdapps packages to which this package
#   is also part of. Hence, make sure that package() entry-point is defined
#   before executing the following lines.
packages = []
pkgs = pkg.WorkingSet().by_key # A dictionary of pkg-name and object
for pkgname, d in sorted( list( pkgs.items() ), key=lambda x : x[0] ):
    info = h.call_entrypoint(d,  'pluggdapps', 'package' )
    if info == None : continue
    __import__( pkgname )
    packages.append( pkgname )

# Load modules
import pluggdapps.platform
import pluggdapps.cookie
import pluggdapps.request
import pluggdapps.response
import pluggdapps.webapp
import pluggdapps.rootapp
import pluggdapps.errorpage
import pluggdapps.routers
import pluggdapps.unittest
# Load packages
import pluggdapps.commands

# Initialize plugin data structures
plugin_init()

