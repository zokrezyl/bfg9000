import argparse
import subprocess
from functools import partial

from . import tool
from .common import SimpleCommand
from .conan import parse_build_info
from .. import log, options as opts, shell
from ..exceptions import PackageResolutionError, PackageVersionError
from ..objutils import memoize
from ..packages import Package, PackageKind
from ..path import Path, Root, InstallRoot
from ..versioning import check_version, Version


@tool('pkg_config')
class PkgConfig(SimpleCommand):
    _options = {
        'version': ['--modversion'],
        'cflags': ['--cflags'],
        'lib_dirs': ['--libs-only-L'],
        'ldflags': ['--libs-only-L', '--libs-only-other'],
        'ldlibs': ['--libs-only-l'],
        'path': ['--variable=pcfiledir'],
        'prefix': ['--variable=prefix'],
    }

    def __init__(self, env):
        super().__init__(env, name='pkg_config', env_var='PKG_CONFIG',
                         default='pkg-config')

    def _call(self, cmd, name, type, static=False, msvc_syntax=False):
        result = cmd + [name] + self._options[type]
        if static:
            result.append('--static')
        if msvc_syntax:
            result.append('--msvc-syntax')
        return result


def _check_version(pkg_config, name, specifier):
    try:
        version = Version(pkg_config.run(name, 'version').strip())
    except subprocess.CalledProcessError:
        raise PackageResolutionError("unable to find package '{}'"
                                     .format(name))

    check_version(version, specifier, name, PackageVersionError)
    return version


def _is_conan(env, pkg_config, name):
    pkg_prefix = pkg_config.run(name, 'prefix').strip()

    path = Path('conanbuildinfo.txt', Root.builddir)
    with open(path.string(env.base_dirs)) as f:
        conan_prefix = parse_build_info(
            f, 'rootpath_{}'.format(name)
        )[0]

    return pkg_prefix == conan_prefix


class PkgConfigPackage(Package):
    def __init__(self, name, format, version, specifier, kind, pkg_config):
        self._pkg_config = pkg_config
        self.version = version
        self.specifier = specifier
        self.static = kind == PackageKind.static
        super().__init__(name, format)

    @memoize
    def _call(self, *args, **kwargs):
        return shell.split(self._pkg_config.run(*args, **kwargs).strip(),
                           type=opts.option_list)

    @staticmethod
    def _make_rpath(path):
        return opts.rpath_dir(path)

    def compile_options(self, compiler):
        return self._call(self.name, 'cflags', self.static,
                          compiler.flavor == 'msvc')

    def link_options(self, linker):
        flags = self._call(self.name, 'ldflags', self.static,
                           linker.flavor == 'msvc')

        # XXX: How should we ensure that these libs are linked statically when
        # necessary?
        libs = self._call(self.name, 'ldlibs', self.static,
                          linker.flavor == 'msvc')
        libs = opts.option_list(opts.lib_literal(i) for i in libs)

        if linker.builder.object_format != 'elf' or self.static:
            return flags + libs

        # pkg-config packages don't generally include rpath information, so we
        # need to generate it ourselves.
        dir_args = self._call(self.name, 'lib_dirs', self.static,
                              linker.flavor == 'msvc',
                              env={'PKG_CONFIG_ALLOW_SYSTEM_LIBS': '1'})

        parser = argparse.ArgumentParser()
        parser.add_argument('-L', action='append', dest='lib_dirs')
        lib_dirs = parser.parse_known_args(dir_args)[0].lib_dirs or []
        rpaths = opts.option_list(self._make_rpath(Path(i, Root.absolute))
                                  for i in lib_dirs)

        return flags + libs + rpaths

    def path(self):
        return self._pkg_config.run(self.name, 'path').strip()

    def __repr__(self):
        return '<{}({!r}, {!r})>'.format(
            type(self).__name__, self.name, str(self.version)
        )


class ConanPkgConfigPackage(PkgConfigPackage):
    __lib_install_path = Path('.', InstallRoot.libdir)

    @classmethod
    def _make_rpath(cls, path):
        return opts.rpath_dual_dir(path, cls.__lib_install_path)


def resolve(env, name, format, version=None, kind=PackageKind.any):
    pkg_config = env.tool('pkg_config')
    found_version = _check_version(pkg_config, name, version)
    pkg_type = (ConanPkgConfigPackage if _is_conan(env, pkg_config, name) else
                PkgConfigPackage)
    package = pkg_type(name, format, found_version, version, kind, pkg_config)

    log.info('found package {!r} version {} via pkg-config in {!r}'
             .format(package.name, package.version, package.path()))
    return package
