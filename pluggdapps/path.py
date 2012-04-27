# -*- coding: utf-8 -*-

import sys, pkg_resources, logging, imp
from   os.path  import isabs, join, split, abspath, isdir, exists
from   os       import listdir

from   pluggdapps.compat    import string_types

log = logging.getLogger( __name__ )

ignore_types = [ imp.C_EXTENSION, imp.C_BUILTIN ]
init_names = [ '__init__%s' % x[0] for x in imp.get_suffixes() 
                                   if x[0] and x[2] not in ignore_types ]

def package_path( package ):
    """Compute directory path to package. To avoid repeating the same
    computing, the abspath is cached on the package object."""
    cachedpath = getattr(package, '__abspath__', None)
    if cachedpath : return cachedpath
    abspath = pkg_resources.resource_filename( package.__name__, '' )
    # pkg_resources doesn't care whether we feed it a package
    # name or a module name within the package, the result
    # will be the same: a directory name to the package
    package.__abspath__ = abspath
    return abspath

def caller_module( level=2, sys=sys ):
    module_globals = sys._getframe(level).f_globals
    module_name = module_globals.get('__name__') or '__main__'
    module = sys.modules[module_name]
    return module

def caller_path( path, level=2 ):
    if isabs( path ) : return path
    module = caller_module( level+1 )
    prefix = package_path(module)
    path = join( prefix, path )
    return path

def package_name( pkg_or_module ):
    """If this function is passed a module, return the dotted Python
    package name of the package in which the module lives. If this
    function is passed a package, return the dotted Python package
    name of the package itself."""
    if pkg_or_module is None or pkg_or_module.__name__ == '__main__':
        return '__main__'
    pkg_filename = pkg_or_module.__file__
    pkg_name = pkg_or_module.__name__
    splitted = split(pkg_filename)
    if splitted[-1] in init_names:
        # it's a package
        return pkg_name
    return pkg_name.rsplit('.', 1)[0]

def package_of( pkg_or_module ):
    """Return the package of a module or return the package itself """
    pkg_name = package_name(pkg_or_module)
    __import__(pkg_name)
    return sys.modules[pkg_name]

def caller_package( level=2 ):
    """``level`` always defaults to 2. Think about it, how can it default to
    something else ?"""
    # caller_module in arglist for tests
    module = caller_module(level+1)
    f = getattr( module, '__file__', '' )
    if (('__init__.py' in f) or ('__init__$py' in f)): # empty at >>>
        # Module is a package
        return module
    # Go up one level to get package
    package_name = module.__name__.rsplit('.', 1)[0]
    return sys.modules[package_name]

class _CALLER_PACKAGE(object):
    def __repr__(self): # pragma: no cover (for docs)
        return 'pyramid.path.CALLER_PACKAGE'

CALLER_PACKAGE = _CALLER_PACKAGE()

class Package(object):
    """The constructor accepts a single argument named ``package`` which may be
    any of,

    - A fully qualified (not relative) dotted name string to a module or package
    - a Python module or package object
    - The value ``None``
    - The constant value :attr:`pluggdapps.asset.CALLER_PACKAGE`.

    The default value is :attr:`pluggdapps.asset.CALLER_PACKAGE`.

    If package input is not provided, then caller's package is assumed."""

    def __init__( self, package=CALLER_PACKAGE ):
        if isinstance(package, string_types):
            __import__(package) # Could be a package or module
            self.package = package_of( sys.modules[package] )
        else :
            self.package = package

    def get_package_name(self):
        if self.package is CALLER_PACKAGE :
            package_name = caller_package().__name__
        else:
            package_name = self.package.__name__
        return package_name

    def get_package(self):
        if self.package is CALLER_PACKAGE:
            package = caller_package()
        else:
            package = self.package
        return package


class AssetResolver( Package ):
    """Resolve :term:`asset specification` to :term:`asset descriptor`.

    The ``package`` is used when a relative asset specification is supplied
    to the :meth:`pluggdapps.asset.AssetResolver.resolve` method. An asset
    specification without a colon in it is treated as relative.

    If the value ``None`` is supplied as the ``package``, the resolver will
    only be able to resolve fully qualified (not relative) asset
    specifications.  Any attempt to resolve a relative asset specification
    when the ``package`` is ``None`` will result in an exception.

    If the value :attr:`pluggdapps.asset.CALLER_PACKAGE` is supplied as the
    ``package``, the resolver will treat relative asset specifications as
    relative to the caller of the :meth:`pluggdapps.asset.AssetResolver.resolve`
    method.

    If a *module* or *module name* (as opposed to a package or package name)
    is supplied as ``package``, its containing package is computed and this
    package used to derive the package name (all names are resolved relative
    to packages, never to modules).  For example, if the ``package`` argument
    to this type was passed the string ``xml.dom.expatbuilder``, and
    ``template.pt`` is supplied to the
    :meth:`pluggdapps.path.AssetResolver.resolve` method, the resulting absolute
    asset spec would be ``xml.minidom:template.pt``, because
    ``xml.dom.expatbuilder`` is a module object, not a package object.

    If a *package* or *package name* (as opposed to a module or module name)
    is supplied as ``package``, this package will be used to compute relative
    asset specifications.  For example, if the ``package`` argument to this
    type was passed the string ``xml.dom``, and ``template.pt`` is supplied
    to the :meth:`pluggdapps.path.AssetResolver.resolve` method, the resulting
    absolute asset spec would be ``xml.minidom:template.pt``.
    """

    def resolve( self, spec ):
        """Resolve the asset spec named as ``spec`` to an object that has the
        attributes and methods described in
        :class:`pluggdapps.interfaces.IAssetDescriptor`.

        If ``spec`` is an absolute filename
        (e.g. ``/path/to/myproject/templates/foo.pt``) or an absolute asset
        spec (e.g. ``myproject:templates.foo.pt``), an asset descriptor is
        returned without taking into account the ``package`` passed to this
        class' constructor.

        If ``spec`` is a *relative* asset specification (an asset
        specification without a ``:`` in it, e.g. ``templates/foo.pt``), the
        ``package`` argument of the constructor is used as the the package
        portion of the asset spec.  For example:

        .. code-block:: python

           a = AssetResolver('myproject')
           resolver = a.resolve('templates/foo.pt')
           print resolver.abspath()
           # -> /path/to/myproject/templates/foo.pt

        If the AssetResolver is constructed without a ``package`` argument of
        ``None``, and a relative asset specification is passed to ``resolve``,
        an exception is raised.
        """
        if isabs(spec): return FSAssetDescriptor(spec)
        path = spec
        if ':' in path:
            package_name, path = spec.split(':', 1)
        else:
            package_name = self.get_package_name()
        return PkgResourcesAssetDescriptor( package_name, path )


class DottedNameResolver( Package ):
    """ A class used to resolve a :term:`dotted Python name` to a package or
    module object.

    The ``package`` is used when a relative dotted name is supplied to the
    :meth:`~pyramid.path.DottedNameResolver.resolve` method.  A dotted name
    which has a ``.`` (dot) or ``:`` (colon) as its first character is
    treated as relative.

    If the value ``None`` is supplied as the ``package``, the resolver will
    only be able to resolve fully qualified (not relative) names.  Any
    attempt to resolve a relative name when the ``package`` is ``None`` will
    result in an :exc:`ValueError` exception.

    If the value :attr:`pyramid.path.CALLER_PACKAGE` is supplied as the
    ``package``, the resolver will treat relative dotted names as relative to
    the caller of the :meth:`~pyramid.path.DottedNameResolver.resolve`
    method.

    If a *module* or *module name* (as opposed to a package or package name)
    is supplied as ``package``, its containing package is computed and this
    package used to derive the package name (all names are resolved relative
    to packages, never to modules).  For example, if the ``package`` argument
    to this type was passed the string ``xml.dom.expatbuilder``, and
    ``.mindom`` is supplied to the
    :meth:`~pyramid.path.DottedNameResolver.resolve` method, the resulting
    import would be for ``xml.minidom``, because ``xml.dom.expatbuilder`` is
    a module object, not a package object.

    If a *package* or *package name* (as opposed to a module or module name)
    is supplied as ``package``, this package will be used to relative compute
    dotted names.  For example, if the ``package`` argument to this type was
    passed the string ``xml.dom``, and ``.minidom`` is supplied to the
    :meth:`~pyramid.path.DottedNameResolver.resolve` method, the resulting
    import would be for ``xml.minidom``.
    """

    def resolve(self, dotted):
        """This method resolves a dotted name reference to a global Python
        object (an object which can be imported) to the object itself.

        Two dotted name styles are supported:

        - ``pkg_resources``-style dotted names where non-module attributes
          of a package are separated from the rest of the path using a ``:``
          e.g. ``package.module:attr``.

        - ``zope.dottedname``-style dotted names where non-module
          attributes of a package are separated from the rest of the path
          using a ``.`` e.g. ``package.module.attr``.

        These styles can be used interchangeably.  If the supplied name
        contains a ``:`` (colon), the ``pkg_resources`` resolution
        mechanism will be chosen, otherwise the ``zope.dottedname``
        resolution mechanism will be chosen.

        If the ``dotted`` argument passed to this method is not a string, a
        :exc:`ValueError` will be raised.

        When a dotted name cannot be resolved, a :exc:`ValueError` error is
        raised.

        Example:

        .. code-block:: python

           r = DottedNameResolver()
           v = r.resolve('xml') # v is the xml module

        """
        if not isinstance(dotted, string_types):
            raise ValueError('%r is not a string' % (dotted,))
        package = self.package
        if package is CALLER_PACKAGE:
            package = caller_package()
        return self._resolve(dotted, package)

    def maybe_resolve(self, dotted):
        """
        This method behaves just like
        :meth:`~pyramid.path.DottedNameResolver.resolve`, except if the
        ``dotted`` value passed is not a string, it is simply returned.  For
        example:

        .. code-block:: python

           import xml
           r = DottedNameResolver()
           v = r.maybe_resolve(xml)
           # v is the xml module; no exception raised
        """
        if isinstance(dotted, string_types):
            package = self.package
            if package is CALLER_PACKAGE:
                package = caller_package()
            return self._resolve(dotted, package)
        return dotted

    def _resolve(self, dotted, package):
        if ':' in dotted:
            return self._pkg_resources_style(dotted, package)
        else:
            return self._zope_dottedname_style(dotted, package)

    def _pkg_resources_style(self, value, package):
        """ package.module:attr style """
        if value.startswith('.') or value.startswith(':'):
            if not package:
                raise ValueError(
                    'relative name %r irresolveable without package' % (value,)
                    )
            if value in ['.', ':']:
                value = package.__name__
            else:
                value = package.__name__ + value
        return pkg_resources.EntryPoint.parse(
            'x=%s' % value).load(False)

    def _zope_dottedname_style(self, value, package):
        """ package.module.attr style """
        module = getattr(package, '__name__', None) # package may be None
        if not module:
            module = None
        if value == '.':
            if module is None:
                raise ValueError(
                    'relative name %r irresolveable without package' % (value,)
                )
            name = module.split('.')
        else:
            name = value.split('.')
            if not name[0]:
                if module is None:
                    raise ValueError(
                        'relative name %r irresolveable without '
                        'package' % (value,)
                        )
                module = module.split('.')
                name.pop(0)
                while not name[0]:
                    module.pop()
                    name.pop(0)
                name = module + name

        used = name.pop(0)
        found = __import__(used)
        for n in name:
            used += '.' + n
            try:
                found = getattr(found, n)
            except AttributeError:
                __import__(used)
                found = getattr(found, n) # pragma: no cover

        return found

class PkgResourcesAssetDescriptor(object):
    def __init__(self, pkg_name, path):
        self.pkg_name = pkg_name
        self.path = path

    def absspec(self):
        return '%s:%s' % (self.pkg_name, self.path)

    def abspath(self):
        return pkg_resources.resource_filename(self.pkg_name, self.path)

    def stream(self):
        return pkg_resources.resource_stream(self.pkg_name, self.path)

    def isdir(self):
        return pkg_resources.resource_isdir(self.pkg_name, self.path)

    def listdir(self):
        return pkg_resources.resource_listdir(self.pkg_name, self.path)

    def exists(self):
        return pkg_resources.resource_exists(self.pkg_name, self.path)


class FSAssetDescriptor(object):
    def __init__(self, path):
        self.path = abspath(path)

    def absspec(self):
        raise NotImplementedError

    def abspath(self):
        return self.path

    def stream(self):
        return open(self.path, 'rb')

    def isdir(self):
        return isdir(self.path)

    def listdir(self):
        return listdir(self.path)

    def exists(self):
        return exists(self.path)


# Unit-test
from pluggdapps.unittest import UnitTestBase
from os.path import dirname, join

class UnitTest_Path( UnitTestBase ):

    def test( self ):
        self.test_package_path()
        self.test_caller_module()
        self.test_caller_path()
        self.test_package_name()
        self.test_package_of()
        self.test_caller_package()

    def test_package_path( self ):
        import pluggdapps.commands.unittest
        log.info("Testing package_path() ...")
        assert package_path(sys.modules[self.__module__]) == dirname(__file__)
        refpath = join( dirname(__file__), 'commands', )
        assert package_path( pluggdapps.commands.unittest ) == refpath

    def test_caller_module( self ):
        import pluggdapps.path
        log.info("Testing caller_module() ...")
        assert caller_module(1) == sys.modules['pluggdapps.path']
        assert caller_module(2) == sys.modules['pluggdapps.path']
        assert caller_module(3) == sys.modules['pluggdapps.commands.unittest']
        assert caller_module(4) == sys.modules['pluggdapps.commands.unittest']

    def test_caller_path( self ):
        log.info("Testing caller_path() ...")
        unittestpath = join( dirname(__file__), 'commands', 'unittest.py' )
        assert caller_path('path.py', 1) == join(dirname(__file__), 'path.py')
        assert caller_path('path.py', 2) == join(dirname(__file__), 'path.py')
        assert caller_path('unittest.py', 3) == unittestpath
        assert caller_path('unittest.py', 4) == unittestpath

    def test_package_name( self ):
        import pluggdapps.commands
        import pluggdapps.commands.unittest
        import os, os.path
        log.info("Testing package_name() ...")
        assert package_name(pluggdapps.commands) == 'pluggdapps.commands'
        assert package_name(pluggdapps.commands.unittest) == 'pluggdapps.commands'
        assert package_name(os.path) == 'posixpath'
        assert package_name(os) == 'os'

    def test_package_of( self ):
        import pluggdapps.commands
        import pluggdapps.commands.unittest
        import os, os.path, posixpath
        log.info("Testing package_of() ...")
        assert package_of(pluggdapps.commands) == pluggdapps.commands
        assert package_of(pluggdapps.commands.unittest) == pluggdapps.commands
        assert package_of(os.path) == posixpath
        assert package_of(os) == os

    def test_caller_package( self ):
        log.info("Testing caller_package() ...")
        assert caller_package(1) == sys.modules['pluggdapps']
        assert caller_package(2) == sys.modules['pluggdapps']
        assert caller_package(3) == sys.modules['pluggdapps.commands']
        assert caller_package(4) == sys.modules['pluggdapps.commands']

