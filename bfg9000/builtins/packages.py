import re
import warnings

from . import builtin
from .. import options as opts
from ..exceptions import PackageResolutionError, PackageVersionError
from ..file_types import Executable
from ..iterutils import default_sentinel, listify
from ..objutils import objectify
from ..packages import CommonPackage, Framework, Package, PackageKind
from ..path import Path, Root
from ..shell import which
from ..versioning import check_version, SpecifierSet, Version


@builtin.function()
@builtin.type(Package)
def package(context, name, version=None, lang=None, kind=PackageKind.any.name,
            headers=default_sentinel, libs=default_sentinel):
    version = objectify(version or '', SpecifierSet)
    kind = PackageKind[kind]

    if ( headers is not default_sentinel or
         libs is not default_sentinel ):  # pragma: no cover
        # TODO: Remove this after 0.6 is released.
        warnings.warn('"headers" and "libs" are deprecated; use mopack.yml ' +
                      'file instead')

    if lang is None:
        lang = context.build['project']['lang']

    resolver = context.env.builder(lang).packages
    return resolver.resolve(name, None, version, kind)


@builtin.function()
@builtin.type(Executable)
def system_executable(context, name, format=None):
    env = context.env
    return Executable(
        Path(which([[name]], env.variables, resolve=True)[0], Root.absolute),
        format or env.target_platform.object_format
    )


@builtin.function()
def framework(context, name, suffix=None):
    env = context.env
    if not env.target_platform.has_frameworks:
        raise PackageResolutionError("{} platform doesn't support frameworks"
                                     .format(env.target_platform.name))

    framework = Framework(name, suffix)
    return CommonPackage(framework.full_name,
                         format=env.target_platform.object_format,
                         link_options=opts.option_list(opts.lib(framework)))


def _boost_version(headers, required_version):
    for header in headers:
        version_hpp = header.path.append('boost').append('version.hpp')
        with open(version_hpp.string()) as f:
            for line in f:
                m = re.match(r'#\s*define\s+BOOST_LIB_VERSION\s+"([\d_]+)"',
                             line)
                if m:
                    version = Version(m.group(1).replace('_', '.'))
                    check_version(version, required_version, 'boost',
                                  PackageVersionError)
                    return version
    raise PackageVersionError('unable to parse "boost/version.hpp"')


@builtin.function()
def boost_package(context, name=None, version=None):
    name = listify(name)
    version = objectify(version or '', SpecifierSet)
    env = context.env

    extra_kwargs = {}
    if env.target_platform.family == 'windows':
        if not env.builder('c++').auto_link:  # pragma: no cover
            # XXX: Don't require auto-link.
            raise PackageResolutionError('Boost on Windows requires auto-link')
        extra_kwargs['can_auto_link'] = True

    resolver = env.builder('c++').packages
    pkg = resolver.resolve('boost', name, version, PackageKind.any,
                           get_version=_boost_version, **extra_kwargs)

    if ( isinstance(pkg, CommonPackage) and
         env.target_platform.family == 'posix' and 'thread' in name ):
        # XXX: Handle this in a better way (possibly in mopack?).
        pkg._compile_options.insert(0, opts.pthread())
        pkg._link_options.insert(0, opts.pthread())

    return pkg
