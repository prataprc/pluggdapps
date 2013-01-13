# -*- coding: utf-8 -*-

# This file is subject to the terms and conditions defined in
# file 'LICENSE', which is part of this source code package.
#       Copyright (c) 2011 R Pratap Chakravarthy


"""Web-application to host static web documents like HTML, CSS,
JavaScript and various image files. All of these files are static content and
subjected to content negotiation.
"""

# - Make sure that to import this package in parent package's __init__ 
#   module.
# - Import necessary modules from 'docroot' web-application so as to load
#   their plugins and interfaces during pluggdapps-bootup.

import pluggdapps.docroot.docroot
import pluggdapps.docroot.router