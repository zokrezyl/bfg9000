from collections import namedtuple
from unittest import mock

from .common import AlwaysEqual, AttrDict, BuiltinTest
from bfg9000 import file_types, options as opts
from bfg9000.builtins import compile, link, packages, project  # noqa
from bfg9000.environment import LibraryMode
from bfg9000.iterutils import listify, unlistify
from bfg9000.packages import CommonPackage
from bfg9000.path import Path, Root

MockCompile = namedtuple('MockCompile', ['file'])


def mock_which(*args, **kwargs):
    return ['command']


def mock_execute(*args, **kwargs):
    return 'version'


class CompileTest(BuiltinTest):
    def output_file(self, name, step={}, lang='c++', mode=None, extra={}):
        compiler = getattr(self.env.builder(lang), mode or self.mode)
        step = AttrDict(**step)

        output = compiler.output_file(name, step)
        public_output = compiler.post_build(self.build, [], output, step)

        result = [i for i in listify(public_output or output) if not i.private]
        for i in result:
            for k, v in extra.items():
                setattr(i, k, v)
        return unlistify(result)


class TestObjectFile(CompileTest):
    mode = 'compiler'

    def test_identity(self):
        expected = file_types.ObjectFile(Path('object', Root.srcdir), None)
        self.assertIs(self.context['object_file'](expected), expected)

    def test_src_file(self):
        expected = file_types.ObjectFile(
            Path('object', Root.srcdir),
            self.env.target_platform.object_format, 'c'
        )
        self.assertSameFile(self.context['object_file']('object'), expected)
        self.assertEqual(list(self.build.sources()), [self.bfgfile, expected])

        self.context['project'](lang='c++')
        expected.lang = 'c++'
        self.assertSameFile(self.context['object_file']('object'), expected)

    def test_no_dist(self):
        expected = file_types.ObjectFile(
            Path('object', Root.srcdir),
            self.env.target_platform.object_format, 'c'
        )
        self.assertSameFile(self.context['object_file']('object', dist=False),
                            expected)
        self.assertEqual(list(self.build.sources()), [self.bfgfile])

    def test_make_simple(self):
        result = self.context['object_file'](file='main.cpp')
        self.assertSameFile(result, self.output_file('main'))

        result = self.context['object_file']('object', 'main.cpp')
        self.assertSameFile(result, self.output_file('object'))

        src = self.context['source_file']('main.cpp')
        result = self.context['object_file']('object', src)
        self.assertSameFile(result, self.output_file('object'))

    def test_make_no_lang(self):
        result = self.context['object_file']('object', 'main.goofy',
                                             lang='c++')
        self.assertSameFile(result, self.output_file('object'))

        self.assertRaises(ValueError, self.context['object_file'], 'object',
                          'main.goofy')

        src = self.context['source_file']('main.goofy')
        self.assertRaises(ValueError, self.context['object_file'], 'object',
                          src)

    def test_make_override_lang(self):
        src = self.context['source_file']('main.c', 'c')
        result = self.context['object_file']('object', src, lang='c++')
        self.assertSameFile(result, self.output_file('object'))
        self.assertEqual(result.creator.compiler.lang, 'c++')

    def test_make_directory(self):
        object_file = self.context['object_file']

        result = object_file(file='main.cpp', directory='dir')
        self.assertSameFile(result, self.output_file('dir/main'))

        src = self.context['source_file']('main.cpp')
        result = object_file(file=src, directory='dir')
        self.assertSameFile(result, self.output_file('dir/main'))

        result = object_file(file='main.cpp', directory='dir/')
        self.assertSameFile(result, self.output_file('dir/main'))

        result = object_file(file='main.cpp', directory=Path('dir'))
        self.assertSameFile(result, self.output_file('dir/main'))

        result = object_file(file='dir1/main.cpp', directory='dir2')
        self.assertSameFile(result, self.output_file('dir2/dir1/main'))

        result = object_file('object', 'main.cpp', directory='dir')
        self.assertSameFile(result, self.output_file('object'))

        self.assertRaises(ValueError, object_file, file='main.cpp',
                          directory=Path('dir', Root.srcdir))

    def test_make_submodule(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            object_file = self.context['object_file']

            result = object_file(file='main.cpp')
            self.assertSameFile(result, self.output_file('dir/main'))
            result = object_file(file='sub/main.cpp')
            self.assertSameFile(result, self.output_file('dir/sub/main'))
            result = object_file(file='../main.cpp')
            self.assertSameFile(result, self.output_file('main'))

            result = object_file('object', 'main.cpp')
            self.assertSameFile(result, self.output_file('dir/object'))
            result = object_file('../object', 'main.cpp')
            self.assertSameFile(result, self.output_file('object'))

            result = object_file(file='main.cpp', directory='sub')
            self.assertSameFile(result, self.output_file('dir/sub/main'))
            result = object_file(file='foo/main.cpp', directory='sub')
            self.assertSameFile(result, self.output_file('dir/sub/foo/main'))
            result = object_file(file='../main.cpp', directory='sub')
            self.assertSameFile(result, self.output_file('dir/sub/PAR/main'))

            result = object_file(file='main.cpp', directory=Path('dir2'))
            self.assertSameFile(result, self.output_file('dir2/dir/main'))
            result = object_file(file='sub/main.cpp', directory=Path('dir2'))
            self.assertSameFile(result, self.output_file('dir2/dir/sub/main'))
            result = object_file(file='../main.cpp', directory=Path('dir2'))
            self.assertSameFile(result, self.output_file('dir2/main'))

            result = object_file(file='main.cpp', directory=Path('dir'))
            self.assertSameFile(result, self.output_file('dir/dir/main'))
            result = object_file(file='sub/main.cpp', directory=Path('dir'))
            self.assertSameFile(result, self.output_file('dir/dir/sub/main'))
            result = object_file(file='../main.cpp', directory=Path('dir'))
            self.assertSameFile(result, self.output_file('dir/main'))

    def test_includes(self):
        object_file = self.context['object_file']

        result = object_file(file='main.cpp', includes='include')
        self.assertEqual(result.creator.includes, [
            file_types.HeaderDirectory(Path('include', Root.srcdir))
        ])
        self.assertEqual(result.creator.include_deps, [])

        hdr = self.context['header_file']('include/main.hpp')
        result = object_file(file='main.cpp', includes=hdr)
        self.assertEqual(result.creator.includes, [
            file_types.HeaderDirectory(Path('include', Root.srcdir))
        ])
        self.assertEqual(result.creator.include_deps, [hdr])

        inc = self.context['header_directory']('include')
        inc.creator = 'foo'
        result = object_file(file='main.cpp', includes=inc)
        self.assertEqual(result.creator.includes, [inc])
        self.assertEqual(result.creator.include_deps, [inc])

    def test_include_order(self):
        fmt = self.env.target_platform.object_format
        incdir = opts.include_dir(file_types.HeaderDirectory(
            Path('include', Root.srcdir)
        ))
        pkg_incdir = opts.include_dir(file_types.HeaderDirectory(
            Path('/usr/include', Root.absolute)
        ))
        pkg = CommonPackage('pkg', format=fmt,
                            compile_options=opts.option_list(pkg_incdir))

        result = self.context['object_file'](file='main.cpp',
                                             includes='include', packages=pkg)
        self.assertEqual(result.creator.options,
                         opts.option_list(incdir, pkg_incdir))

    def test_libs(self):
        self.env.library_mode = LibraryMode(True, False)

        result = self.context['object_file'](file='main.java', libs='lib')
        self.assertEqual(result.creator.libs, [
            file_types.StaticLibrary(Path('lib', Root.srcdir), 'java')
        ])

    def test_pch(self):
        pch = file_types.PrecompiledHeader(Path('pch', Root.builddir), 'c')
        pch.object_file = 'foo'

        result = self.context['object_file'](file='main.cpp', pch=pch)
        self.assertIs(result.creator.pch, pch)

        self.assertRaises(TypeError, self.context['object_file'],
                          file='main.java', pch=pch)

    def test_extra_deps(self):
        dep = self.context['generic_file']('dep.txt')
        result = self.context['object_file'](file='main.cpp', extra_deps=[dep])
        self.assertSameFile(result, self.output_file('main'))
        self.assertEqual(result.creator.extra_deps, [dep])

    def test_make_no_name_or_file(self):
        self.assertRaises(TypeError, self.context['object_file'])

    def test_description(self):
        result = self.context['object_file'](
            file='main.cpp', description='my description'
        )
        self.assertEqual(result.creator.description, 'my description')


class TestPrecompiledHeader(CompileTest):
    class MockFile:
        def write(self, data):
            pass

    mode = 'pch_compiler'

    def output_file(self, name, pch_source='main.cpp', *args, **kwargs):
        pch_source_path = Path(name).parent().append(pch_source)
        step = {'pch_source': file_types.SourceFile(pch_source_path, 'c++')}
        return super().output_file(name, step, *args, **kwargs)

    def test_identity(self):
        ex = file_types.PrecompiledHeader(Path('header', Root.srcdir), None)
        self.assertIs(self.context['precompiled_header'](ex), ex)

    def test_src_file(self):
        expected = file_types.PrecompiledHeader(
            Path('header', Root.srcdir), 'c'
        )
        self.assertSameFile(self.context['precompiled_header']('header'),
                            expected)
        self.assertEqual(list(self.build.sources()), [self.bfgfile, expected])

        self.context['project'](lang='c++')
        expected.lang = 'c++'
        self.assertSameFile(self.context['precompiled_header']('header'),
                            expected)

    def test_no_dist(self):
        expected = file_types.PrecompiledHeader(
            Path('header', Root.srcdir), 'c'
        )
        self.assertSameFile(
            self.context['precompiled_header']('header', dist=False),
            expected
        )
        self.assertEqual(list(self.build.sources()), [self.bfgfile])

    def test_make_simple(self):
        with mock.patch('bfg9000.builtins.file_types.make_immediate_file',
                        return_value=self.MockFile()):
            pch = self.context['precompiled_header']

            result = pch(file='main.hpp')
            self.assertSameFile(result, self.output_file('main.hpp'))

            result = pch('object', 'main.hpp')
            self.assertSameFile(result, self.output_file('object'))

            src = self.context['header_file']('main.hpp')
            result = pch('object', src)
            self.assertSameFile(result, self.output_file('object'))

    def test_make_no_lang(self):
        with mock.patch('bfg9000.builtins.file_types.make_immediate_file',
                        return_value=self.MockFile()):
            pch = self.context['precompiled_header']

            result = pch('object', 'main.goofy', lang='c++')
            self.assertSameFile(result, self.output_file('object'))
            self.assertRaises(ValueError, pch, 'object', 'main.goofy')

            src = self.context['header_file']('main.goofy')
            self.assertRaises(ValueError, pch, 'object', src)

    def test_make_override_lang(self):
        with mock.patch('bfg9000.builtins.file_types.make_immediate_file',
                        return_value=self.MockFile()):
            pch = self.context['precompiled_header']

            src = self.context['header_file']('main.h', 'c')
            result = pch('object', src, lang='c++')
            self.assertSameFile(result, self.output_file('object'))
            self.assertEqual(result.creator.compiler.lang, 'c++')

    def test_make_directory(self):
        with mock.patch('bfg9000.builtins.file_types.make_immediate_file',
                        return_value=self.MockFile()):
            pch = self.context['precompiled_header']

            result = pch(file='main.hpp', directory='dir')
            self.assertSameFile(result, self.output_file('dir/main.hpp'))

            src = self.context['header_file']('main.hpp')
            result = pch(file=src, directory='dir')
            self.assertSameFile(result, self.output_file('dir/main.hpp'))

            result = pch(file='main.hpp', directory='dir/')
            self.assertSameFile(result, self.output_file('dir/main.hpp'))

            result = pch(file='main.hpp', directory=Path('dir'))
            self.assertSameFile(result, self.output_file('dir/main.hpp'))

            result = pch(file='dir1/main.hpp', directory='dir2')
            self.assertSameFile(result, self.output_file('dir2/dir1/main.hpp'))

            result = pch('object', 'main.hpp', directory='dir')
            self.assertSameFile(result, self.output_file('object'))

            self.assertRaises(ValueError, pch, file='main.hpp',
                              directory=Path('dir', Root.srcdir))

    def test_make_submodule(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            pch = self.context['precompiled_header']

            res = pch(file='main.hpp')
            self.assertSameFile(res, self.output_file('dir/main.hpp'))
            res = pch(file='sub/main.hpp')
            self.assertSameFile(res, self.output_file('dir/sub/main.hpp'))
            res = pch(file='../main.hpp')
            self.assertSameFile(res, self.output_file('main.hpp'))

            res = pch('object', 'main.hpp')
            self.assertSameFile(res, self.output_file('dir/object'))
            res = pch('../object', 'main.hpp')
            self.assertSameFile(res, self.output_file('object'))

            res = pch(file='main.hpp', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/main.hpp'))
            res = pch(file='foo/main.hpp', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/foo/main.hpp'))
            res = pch(file='../main.hpp', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/PAR/main.hpp'))

            res = pch(file='main.hpp', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/dir/main.hpp'))
            res = pch(file='sub/main.hpp', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/dir/sub/main.hpp'))
            res = pch(file='../main.hpp', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/main.hpp'))

            res = pch(file='main.hpp', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/dir/main.hpp'))
            res = pch(file='sub/main.hpp', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/dir/sub/main.hpp'))
            res = pch(file='../main.hpp', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/main.hpp'))

    def test_extra_deps(self):
        dep = self.context['generic_file']('dep.txt')
        with mock.patch('bfg9000.builtins.file_types.make_immediate_file',
                        return_value=self.MockFile()):
            pch = self.context['precompiled_header']

            result = pch(file='main.hpp', extra_deps=[dep])
            self.assertSameFile(result, self.output_file('main.hpp'))
            self.assertEqual(result.creator.extra_deps, [dep])

    def test_make_no_name_or_file(self):
        self.assertRaises(TypeError, self.context['precompiled_header'])

    def test_description(self):
        result = self.context['precompiled_header'](
            file='main.hpp', description='my description'
        )
        self.assertEqual(result.creator.description, 'my description')


class TestGeneratedSource(CompileTest):
    mode = 'transpiler'

    def setUp(self):
        super().setUp()
        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            self.env.builder('qrc')

    def output_file(self, name, step={}, lang='qrc', *args, **kwargs):
        return super().output_file(name, step, lang, *args, **kwargs)

    def test_make_simple(self):
        result = self.context['generated_source'](file='file.qrc')
        self.assertSameFile(result, self.output_file('file.cpp'))

        result = self.context['generated_source']('file.qrc')
        self.assertSameFile(result, self.output_file('file.cpp'))

        result = self.context['generated_source']('name.cpp', 'file.qrc')
        self.assertSameFile(result, self.output_file('name.cpp'))

        src = self.context['resource_file']('file.qrc')
        result = self.context['generated_source']('name.cpp', src)
        self.assertSameFile(result, self.output_file('name.cpp'))

    def test_make_no_lang(self):
        gen_src = self.context['generated_source']
        result = gen_src('file.cpp', 'file.goofy', lang='qrc')
        self.assertSameFile(result, self.output_file('file.cpp'))

        self.assertRaises(ValueError, gen_src, 'file.cpp', 'file.goofy')

        src = self.context['resource_file']('file.goofy')
        self.assertRaises(ValueError, gen_src, 'file.cpp', src)

    def test_make_override_lang(self):
        src = self.context['resource_file']('main.ui', 'qtui')
        result = self.context['generated_source']('main.cpp', src, lang='qrc')
        self.assertSameFile(result, self.output_file('main.cpp'))
        self.assertEqual(result.creator.compiler.lang, 'qrc')

    def test_make_directory(self):
        gen_src = self.context['generated_source']

        res = gen_src(file='main.qrc', directory='dir')
        self.assertSameFile(res, self.output_file('dir/main.cpp'))

        src = self.context['resource_file']('main.qrc')
        res = gen_src(file=src, directory='dir')
        self.assertSameFile(res, self.output_file('dir/main.cpp'))

        res = gen_src(file='main.qrc', directory='dir/')
        self.assertSameFile(res, self.output_file('dir/main.cpp'))

        res = gen_src(file='main.qrc', directory=Path('dir'))
        self.assertSameFile(res, self.output_file('dir/main.cpp'))

        res = gen_src(file='dir1/main.qrc', directory='dir2')
        self.assertSameFile(res, self.output_file('dir2/dir1/main.cpp'))

        res = gen_src('name.cpp', 'main.qrc', directory='dir')
        self.assertSameFile(res, self.output_file('name.cpp'))

        self.assertRaises(ValueError, gen_src, file='main.qrc',
                          directory=Path('dir', Root.srcdir))

    def test_make_submodule(self):
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            gen_src = self.context['generated_source']

            res = gen_src(file='main.qrc')
            self.assertSameFile(res, self.output_file('dir/main.cpp'))
            res = gen_src(file='sub/main.qrc')
            self.assertSameFile(res, self.output_file('dir/sub/main.cpp'))
            res = gen_src(file='../main.qrc')
            self.assertSameFile(res, self.output_file('main.cpp'))

            res = gen_src('name.cpp', 'main.qrc')
            self.assertSameFile(res, self.output_file('dir/name.cpp'))
            res = gen_src('../name.cpp', 'main.qrc')
            self.assertSameFile(res, self.output_file('name.cpp'))

            res = gen_src(file='main.qrc', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/main.cpp'))
            res = gen_src(file='foo/main.qrc', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/foo/main.cpp'))
            res = gen_src(file='../main.qrc', directory='sub')
            self.assertSameFile(res, self.output_file('dir/sub/PAR/main.cpp'))

            res = gen_src(file='main.qrc', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/dir/main.cpp'))
            res = gen_src(file='sub/main.qrc', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/dir/sub/main.cpp'))
            res = gen_src(file='../main.qrc', directory=Path('dir2'))
            self.assertSameFile(res, self.output_file('dir2/main.cpp'))

            res = gen_src(file='main.qrc', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/dir/main.cpp'))
            res = gen_src(file='sub/main.qrc', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/dir/sub/main.cpp'))
            res = gen_src(file='../main.qrc', directory=Path('dir'))
            self.assertSameFile(res, self.output_file('dir/main.cpp'))

    def test_description(self):
        result = self.context['generated_source'](file='main.qrc',
                                                  description='my description')
        self.assertEqual(result.creator.description, 'my description')

    def test_extra_deps(self):
        dep = self.context['generic_file']('dep.txt')
        result = self.context['generated_source'](file='file.qrc',
                                                  extra_deps=[dep])
        self.assertSameFile(result, self.output_file('file.cpp'))
        self.assertEqual(result.creator.extra_deps, [dep])


class TestObjectFiles(BuiltinTest):
    def make_file_list(self, make_src=False, prefix=''):
        files = [file_types.ObjectFile(Path(i, Root.srcdir), None)
                 for i in [prefix + 'obj1', prefix + 'obj2']]
        if make_src:
            src_files = [file_types.SourceFile(Path(i, Root.srcdir), None)
                         for i in [prefix + 'src1', prefix + 'src2']]
            for f, s in zip(files, src_files):
                f.creator = MockCompile(s)

        file_list = self.context['object_files'](files)

        if make_src:
            return file_list, files, src_files
        return file_list, files

    def test_initialize(self):
        file_list, files = self.make_file_list()
        self.assertEqual(list(file_list), files)

    def test_getitem_index(self):
        file_list, files = self.make_file_list()
        self.assertEqual(file_list[0], files[0])

    def test_getitem_string(self):
        file_list, files, src_files = self.make_file_list(True)
        self.assertEqual(file_list['src1'], files[0])

    def test_getitem_string_submodule(self):
        file_list, files, src_files = self.make_file_list(True, 'dir/')
        self.assertEqual(file_list['dir/src1'], files[0])
        with self.context.push_path(Path('dir/build.bfg', Root.srcdir)):
            self.assertEqual(file_list['src1'], files[0])

    def test_getitem_path(self):
        file_list, files, src_files = self.make_file_list(True)
        self.assertEqual(file_list[src_files[0].path], files[0])

    def test_getitem_file(self):
        file_list, files, src_files = self.make_file_list(True)
        self.assertEqual(file_list[src_files[0]], files[0])

    def test_getitem_not_found(self):
        file_list, files, src_files = self.make_file_list(True)
        self.assertRaises(IndexError, lambda: file_list[2])
        self.assertRaises(IndexError, lambda: file_list['src3'])
        self.assertRaises(IndexError, lambda: file_list[Path(
            'src3', Root.srcdir
        )])


class TestGeneratedSources(TestObjectFiles):
    def setUp(self):
        super().setUp()
        with mock.patch('bfg9000.shell.which', mock_which), \
             mock.patch('bfg9000.shell.execute', mock_execute):  # noqa
            self.env.builder('qrc')

    def make_file_list(self, return_src=False, prefix=''):
        files = [file_types.SourceFile(Path(i, Root.builddir), 'c++')
                 for i in [prefix + 'src1.cpp', prefix + 'src2.cpp']]
        src_files = [file_types.SourceFile(Path(i, Root.srcdir), 'qrc')
                     for i in [prefix + 'src1', prefix + 'src2']]

        file_list = self.context['generated_sources'](src_files)

        if return_src:
            return file_list, files, src_files
        return file_list, files


class TestMakeBackend(BuiltinTest):
    def test_simple(self):
        makefile = mock.Mock()
        src = self.context['source_file']('main.cpp')

        result = self.context['object_file'](file=src)
        compile.make_compile(result.creator, self.build, makefile,
                             self.env)
        makefile.rule.assert_called_once_with(
            result, [src], [], AlwaysEqual(), {}, None
        )

    def test_dir_sentinel(self):
        makefile = mock.Mock()
        src = self.context['source_file']('dir/main.cpp')

        result = self.context['object_file'](file=src)
        compile.make_compile(result.creator, self.build, makefile,
                             self.env)
        makefile.rule.assert_called_once_with(
            result, [src], [Path('dir/.dir')], AlwaysEqual(), {}, None
        )

    def test_extra_deps(self):
        makefile = mock.Mock()
        dep = self.context['generic_file']('dep.txt')
        src = self.context['source_file']('main.cpp')

        result = self.context['object_file'](file=src, extra_deps=dep)
        compile.make_compile(result.creator, self.build, makefile,
                             self.env)
        makefile.rule.assert_called_once_with(
            result, [src, dep], [], AlwaysEqual(), {}, None
        )


class TestNinjaBackend(BuiltinTest):
    def test_simple(self):
        ninjafile = mock.Mock()
        src = self.context['source_file']('main.cpp')

        result = self.context['object_file'](file=src)
        compile.ninja_compile(result.creator, self.build, ninjafile,
                              self.env)
        ninjafile.build.assert_called_once_with(
            output=[result], rule='cxx', inputs=[src], implicit=[],
            variables={}
        )

    def test_extra_deps(self):
        ninjafile = mock.Mock()
        dep = self.context['generic_file']('dep.txt')
        src = self.context['source_file']('main.cpp')

        result = self.context['object_file'](file=src, extra_deps=dep)
        compile.ninja_compile(result.creator, self.build, ninjafile,
                              self.env)
        ninjafile.build.assert_called_once_with(
            output=[result], rule='cxx', inputs=[src], implicit=[dep],
            variables={}
        )
