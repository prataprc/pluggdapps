# -*- coding: utf-8 -*-

import pkg_resources, logging
from   os.path  import isabs, sep

from   pluggdapps.compat    import string_types
from   pluggdapps.path      import package_name, package_path

log = logging.getLogger( __name__ )

def parse_assetspec( spec, pname ):
    """Parse the asset specification ``spec`` in the context of package name
    ``pname``. If pname is package object, it is resolved as pname.__name__.

    Return a tuple of (packagename, filename), where packagename is the name
    of the package relative to which the file asset ``filename`` is
    located."""

    if os.path.isabs(spec) : return None, spec

    if pname and not isinstance(pname, string_types) :
        pname = pname.__name__ # as package

    filename = spec
    if ':' in spec :
        pname, filename = spec.split(':', 1)
    elif pname is None :
        pname, filename = None, spec
    return pname, filename

def asset_spec_from_abspath( abspath, package ):
    """ Try to convert an absolute path to a resource in a package to
    a resource specification if possible; otherwise return the
    absolute path.  """
    if getattr(package, '__name__', None) == '__main__':
        return abspath
    pp = package_path(package) + sep
    if abspath.startswith(pp):
        relpath = abspath[len(pp):]
        return '%s:%s' % (package_name(package),
                          relpath.replace(sep, '/'))
    return abspath

# bw compat only; use AssetDescriptor.abspath() instead
def abspath_from_asset_spec( spec, pname=None ):
    if pname is None :
        return spec
    pname, filename = resolve_asset_spec( spec, pname )
    if pname is None:
        return filename
    return pkg_resources.resource_filename(pname, filename)
