A roadmap of things to do
=========================

- There is a circular dependancy between pluggdapps, tayra and tayrakit.
  Move webadmin webapp into separate package and remove tayra and tayrakit
  from dependancy.

- fix test cases for pluggdapps so that relchk.sh should be able validate the
  distribution and installation of pluggdapps standalone.

- select, fcntl does not work with mac - needed for pluggdapps builtin http
  server.

- Benchmark pluggdapps with other web-frameworks. sinatra, dynamo, cowboy,
  pyramids, WebPy, Django, Mochiweb, RoR, Express etc ...

- Migrate pluggdapps, tayra, paenv and other dependant packages to python-3.3.
  Looks like there is a tricky dependancy with Jinja2,
    Jinja2 version 2.7 requires python 3.3
    Jinja2 version 2.6 requires python 3.2

- In command-line documentation article indicate that developers should check
  for existing commands before authoring a new-command to avoid duplicating
  names.

- Single-function applications to be developed and demonstrated.
  Publishing Static-web-site / Remote-file-explorer / Publishing repository /
  Discussion forums / Publishing version-control-systems /
  Brandizer to create brand-names using dictionary words.

- Create an article explaining content negotiation protocol in pluggdapps
  web-framework's matchrouter.

- Refer Apache mod_dir and mod_autoindex while developing
  Remote-file-explorer app.

- Netscale, figure out possible ways of exiting netscale platform (document
  them as well) and handle them gracefully inside pluggdapps (which
  will be executing as a separate port-process).

- Implement a native web server. Already there is an evented web-server using
  linux epoll mechanism. But it is yet to be ironed out and tested.
  Code is available in pluggdapps/evserver directory. Move the code to
  separate package and make it available as an IServer plugin.

- man sub-command for pa-script to show help text for interfaces and plugins.

- config sub-command for pa-script should include options to display settings
  help.

- Follow through
  http://rhettinger.wordpress.com/2011/05/26/super-considered-super/
  and work out method-resolution-order using super().

- -*- coding:utf-8 -*- 
  should always be prefixed at the beginning of the file ?

- Add appropriate classifiers.

- Routing, resolve view callable based in media-type. The problem is there can
  be more than one view callable which differ only by their media_type
  predicate. We need a logic in routing code which used Accept request header
  field to choose the highest priority media_type based on qvalue.

- Sphinx documentation, once the modules have stabilised, fix the
  documentation to specifically include classes and functions.

- Use Keep-Alive (deprecated header ?) to set timeout for client's keep-alive
  connections.

- Let log*() methods be available on every instantiated plugins.

- Response header fields are encoded using utf-8 encoding. But looks like the
  specification says that it must be ISO-8859-1.

- pip seems to have a problem, let us say we do,
    pip install --no-index -f <dir> pagd
  under ~/dev/pagd, it does not install pagd package !!

Release check-list 
------------------

- Sphinx doc quick-start, one time activity.
        sphinx-quickstart   # And follow the prompts.
        sphinx-apidoc -f -d 2 -T -o  docs/ pluggdapps $(APIDOC_EXCLUDE_PATH)

- Change the release version in ./CHANGELOG.rst, ./pluggdapps/__init__.py

- Update TODO.rst if any, because both CHANGELOG.rst and TODO.rst are referred
  by README.rst.

- Check whether release changelogs in CHANGELOG.rst have their release-timeline
  logged, atleast uptill the previous release.

- Update setup.py and MANIFEST.in for release

- Make sure that sphinxdoc/modules/ has all the modules that need to be
  documented.

- Enter the virtual environment and upload the source into pypi.
    make upload

- Upload documentation zip.

- Check with relchk.sh whether the system is working fine.

- After making the release, taging the branch, increment the version number.

- Create a tag and push the tagged branch to 
    code.google.com 
    bitbucket.com
    github.com

