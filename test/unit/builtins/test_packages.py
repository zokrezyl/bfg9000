import os
import re
from contextlib import contextmanager
from unittest import mock

from .common import BuiltinTest
from .. import *

from bfg9000 import file_types, options as opts
from bfg9000.build_inputs import BuildInputs
from bfg9000.builtins import builtin, packages, project  # noqa
from bfg9000.exceptions import PackageResolutionError, PackageVersionError
from bfg9000.file_types import HeaderDirectory
from bfg9000.iterutils import first
from bfg9000.packages import CommonPackage, Framework
from bfg9000.path import abspath, Path, Root
from bfg9000.versioning import SpecifierSet, Version


def mock_which(names, *args, **kwargs):
    return [os.path.abspath('/' + first(first(names)))]


def mock_execute(args, **kwargs):
    prog = os.path.basename(args[0])
    if prog in ('cc', 'c++'):
        if args[-1] == '--version':
            return ('gcc (Ubuntu 5.4.0-6ubuntu1~16.04.9) 5.4.0 20160609\n' +
                    'Copyright (C) 2015 Free Software Foundation, Inc.\n')
        elif args[-1] == '/?':
            raise OSError()
        elif args[-1] == '-Wl,--version':
            return '', '/usr/bin/ld --version\n'
        elif args[-1] == '-print-search-dirs':
            return 'libraries: =/usr/lib\n'
        elif args[-1] == '-print-sysroot':
            return '/\n'
    elif prog == 'ld':
        if args[-1] == '--verbose':
            return 'SEARCH_DIR("/usr")\n'
    elif prog == 'cl':
        if args[-1] == '--version':
            raise OSError()
        elif args[-1] == '/?':
            return ('Microsoft (R) C/C++ Optimizing Compiler Version ' +
                    '19.12.25831 for x86')
    elif prog == 'mopack':
        if args[1] == 'usage':
            return ('{"type": "system", "include_path": [], ' +
                    '"library_path": [], "headers": [], "libraries": []}\n')
    elif prog == 'pkg-config':
        if args[1] == 'boost':
            raise OSError()
        if args[-1] == '--modversion':
            return '1.2.3\n'
        elif args[-1] == '--variable=pcfiledir':
            return '/path/to/pkg-config'

    raise ValueError('unknown command: {}'.format(args))


class TestFramework(TestCase):
    def _make_context(self, env):
        build = BuildInputs(env, Path('build.bfg', Root.srcdir))
        return builtin.BuildContext(env, build, None)

    def test_framework(self):
        env = make_env('macos')
        context = self._make_context(env)

        self.assertEqual(
            context['framework']('name'),
            CommonPackage('name', format=env.target_platform.object_format,
                          link_options=opts.option_list(opts.lib(
                              Framework('name')
                          )))
        )

    def test_framework_suffix(self):
        env = make_env('macos')
        context = self._make_context(env)

        self.assertEqual(
            context['framework']('name', 'suffix'),
            CommonPackage('name,suffix',
                          format=env.target_platform.object_format,
                          link_options=opts.option_list(opts.lib(
                              Framework('name', 'suffix')
                          )))
        )

    def test_frameworks_unsupported(self):
        env = make_env('linux')
        context = self._make_context(env)

        with self.assertRaises(PackageResolutionError):
            context['framework']('name')

        with self.assertRaises(PackageResolutionError):
            context['framework']('name', 'suffix')


class TestPackage(BuiltinTest):
    clear_variables = True

    def test_name(self):
        with mock.patch('bfg9000.shell.execute', mock_execute), \
             mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('logging.log'):  # noqa
            pkg = self.context['package']('name')
            self.assertEqual(pkg.name, 'name')
            self.assertEqual(pkg.version, Version('1.2.3'))
            self.assertEqual(pkg.specifier, SpecifierSet())
            self.assertEqual(pkg.static, False)

    def test_version(self):
        with mock.patch('bfg9000.shell.execute', mock_execute), \
             mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('logging.log'):  # noqa
            pkg = self.context['package']('name', version='>1.0')
            self.assertEqual(pkg.name, 'name')
            self.assertEqual(pkg.version, Version('1.2.3'))
            self.assertEqual(pkg.specifier, SpecifierSet('>1.0'))
            self.assertEqual(pkg.static, False)

    def test_lang(self):
        with mock.patch('bfg9000.shell.execute', mock_execute), \
             mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('logging.log'):  # noqa
            pkg = self.context['package']('name', lang='c++')
            self.assertEqual(pkg.name, 'name')
            self.assertEqual(pkg.version, Version('1.2.3'))
            self.assertEqual(pkg.specifier, SpecifierSet())
            self.assertEqual(pkg.static, False)

    def test_kind(self):
        with mock.patch('bfg9000.shell.execute', mock_execute), \
             mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('logging.log'):  # noqa
            pkg = self.context['package']('name', kind='static')
            self.assertEqual(pkg.name, 'name')
            self.assertEqual(pkg.version, Version('1.2.3'))
            self.assertEqual(pkg.specifier, SpecifierSet())
            self.assertEqual(pkg.static, True)

    def test_guess_lang(self):
        @contextmanager
        def mock_context():
            mock_obj = mock.patch.object
            with mock_obj(self.env, 'builder', wraps=self.env.builder) as m, \
                 mock.patch('bfg9000.shell.execute', mock_execute), \
                 mock.patch('bfg9000.shell.which', mock_which), \
                 mock.patch('logging.log'):  # noqa
                yield m

        package = self.context['package']

        with mock_context() as m:
            pkg = package('name')
            self.assertEqual(pkg.name, 'name')
            m.assert_called_once_with('c')

        self.context['project'](lang='c++')
        with mock_context() as m:
            pkg = package('name')
            self.assertEqual(pkg.name, 'name')
            m.assert_called_once_with('c++')

    def test_invalid_kind(self):
        with self.assertRaises(ValueError):
            self.context['package']('name', kind='bad')


class TestBoostPackage(TestCase):
    def _make_context(self, env):
        build = BuildInputs(env, Path('build.bfg', Root.srcdir))
        return builtin.BuildContext(env, build, None)

    def test_boost_version(self):
        data = '#define BOOST_LIB_VERSION "1_23_4"\n'
        with mock.patch('builtins.open', mock_open(read_data=data)):
            hdrs = [HeaderDirectory(abspath('path'))]
            self.assertEqual(packages._boost_version(hdrs, SpecifierSet('')),
                             Version('1.23.4'))

    def test_boost_version_too_old(self):
        data = '#define BOOST_LIB_VERSION "1_23_4"\n'
        with mock.patch('builtins.open', mock_open(read_data=data)):
            hdrs = [HeaderDirectory(abspath('path'))]
            with self.assertRaises(PackageVersionError):
                packages._boost_version(hdrs, SpecifierSet('>=1.30'))

    def test_boost_version_cant_parse(self):
        data = 'foobar\n'
        with mock.patch('builtins.open', mock_open(read_data=data)):
            hdrs = [HeaderDirectory(abspath('path'))]
            with self.assertRaises(PackageVersionError):
                packages._boost_version(hdrs, SpecifierSet(''))

    def test_posix(self):
        env = make_env('linux', clear_variables=True)
        context = self._make_context(env)

        def mock_exists(x):
            x = x.string()
            return bool(re.search(r'[/\\]boost[/\\]version.hpp$', x) or
                        re.search(r'[/\\]libboost_thread', x) or
                        x in ['/usr/include', '/usr/lib'])

        with mock.patch('bfg9000.builtins.packages._boost_version',
                        return_value=Version('1.23')), \
             mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute), \
             mock.patch('bfg9000.tools.cc.exists', mock_exists):  # noqa
            pkg = context['boost_package']('thread')
            self.assertEqual(pkg.name, 'boost(thread)')
            self.assertEqual(pkg.version, Version('1.23'))


class TestSystemExecutable(BuiltinTest):
    def test_name(self):
        with mock.patch('bfg9000.builtins.packages.which', mock_which):
            self.assertEqual(
                self.context['system_executable']('name'),
                file_types.Executable(abspath('/name'),
                                      self.env.target_platform.object_format)
            )

    def test_format(self):
        with mock.patch('bfg9000.builtins.packages.which', mock_which):
            self.assertEqual(
                self.context['system_executable']('name', 'format'),
                file_types.Executable(abspath('/name'), 'format')
            )
