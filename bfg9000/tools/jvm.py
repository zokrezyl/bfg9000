import os
import re
from itertools import chain

from .common import BuildCommand, Builder, check_which, not_buildroot
from .. import log, options as opts, safe_str, shell
from ..builtins.file_types import make_immediate_file
from ..exceptions import PackageResolutionError
from ..file_types import *
from ..iterutils import flatten, iterate, uniques
from ..languages import known_formats
from ..packages import Package
from ..path import Path, Root
from ..versioning import detect_version

_warning_flags = {
    'java': {
        opts.WarningValue.disable: '-nowarn',
        opts.WarningValue.error: '-Werror',
        opts.WarningValue.all: '-Xlint:all',
    },
    'scala': {
        opts.WarningValue.disable: '-nowarn',
        opts.WarningValue.error: '-Xfatal-errors',
        opts.WarningValue.all: '-Xlint:_',
    },
}


class JvmBuilder(Builder):
    def __init__(self, env, langinfo, command, version_output):
        # The default command name to run JVM programs is (usually) the same as
        # the name of the language, so we'll just use that here as the default.
        run_name = langinfo.var('runner').lower()
        run_command = check_which(
            env.getvar(langinfo.var('runner'), langinfo.name),
            kind='{} runner'.format(langinfo.name)
        )

        super().__init__(langinfo.name, *self._parse_brand(
            env, langinfo.name, version_output, run_command
        ))
        self.object_format = 'jvm'

        name = langinfo.var('compiler').lower()
        ldinfo = known_formats['jvm', 'dynamic']

        flags_name = langinfo.var('flags').lower()
        flags = shell.split(env.getvar(langinfo.var('flags'), ''))

        jar_name = ldinfo.var('linker').lower()
        jar_command = check_which(env.getvar(ldinfo.var('linker'), 'jar'),
                                  kind='jar builder')

        jarflags_name = ldinfo.var('flags').lower()
        jarflags = shell.split(env.getvar(ldinfo.var('flags'), 'cfm'))

        self.compiler = JvmCompiler(self, env, name, command, flags_name,
                                    flags)
        self._linker = JarMaker(self, env, jar_name, jar_command,
                                jarflags_name, jarflags)
        self.packages = JvmPackageResolver(self, env, run_command)
        self.runner = JvmRunner(self, env, run_name, run_command)

    @staticmethod
    def _parse_brand(env, lang, version_output, run_command):
        brand = 'unknown'
        version = None
        if lang == 'java':
            try:
                # Get the brand from the run command (rather than the compile
                # command).
                output = env.execute(
                    run_command + ['-version'], stdout=shell.Mode.pipe,
                    stderr=shell.Mode.stdout
                )
                if re.search(r'Java\(TM\) (\w+ )?Runtime Environment', output):
                    brand = 'oracle'
                elif 'OpenJDK Runtime Environment' in output:
                    brand = 'openjdk'
            except (OSError, shell.CalledProcessError):
                pass
            version = detect_version(version_output)
        elif lang == 'scala':
            if 'EPFL' in version_output:
                brand = 'epfl'
                version = detect_version(version_output)
        else:  # pragma: no cover
            raise ValueError('unrecognized language {!r}'.format(lang))

        return brand, version

    @staticmethod
    def check_command(env, command):
        return env.execute(command + ['-version'], stdout=shell.Mode.pipe,
                           stderr=shell.Mode.stdout)

    @property
    def flavor(self):
        return 'jvm'

    @property
    def family(self):
        return 'jvm'

    @property
    def can_dual_link(self):
        return False

    def linker(self, mode):
        if mode == 'static_library':
            raise ValueError('static linking not supported with {}'.format(
                self.brand
            ))
        if mode not in ('executable', 'shared_library'):
            raise KeyError(mode)
        return self._linker


class JvmCompiler(BuildCommand):
    def __init__(self, builder, env, name, command, flags_name, flags):
        super().__init__(builder, env, name, name, command,
                         flags=(flags_name, flags))

    @property
    def deps_flavor(self):
        return None

    @property
    def needs_libs(self):
        return True

    @property
    def accepts_pch(self):
        return False

    def _call(self, cmd, input, output, flags=None):
        jvmoutput = self.env.tool('jvmoutput')
        result = list(chain(
            cmd, self._always_flags, iterate(flags), [input]
        ))
        return jvmoutput(output, result)

    @property
    def _always_flags(self):
        return ['-verbose', '-d', '.']

    def flags(self, options, output=None, mode='normal'):
        flags, class_path = [], []
        for i in options:
            if isinstance(i, opts.lib):
                class_path.append(i.library.path)
            elif isinstance(i, opts.warning):
                for j in i.value:
                    try:
                        flags.append(_warning_flags[self.lang][j])
                    except KeyError:
                        raise ValueError('unsupported warning level {!r}'
                                         .format(j))
            elif isinstance(i, opts.debug):
                flags.append('-g' if self.lang == 'java' else '-g:vars')
            elif isinstance(i, opts.optimize):
                if ( self.lang == 'scala' and
                     (opts.OptimizeValue.size in i.value or
                      opts.OptimizeValue.speed in i.value) ):
                    flags.append('-optimize')
            elif isinstance(i, safe_str.stringy_types):
                flags.append(i)
            else:
                raise TypeError('unknown option type {!r}'.format(type(i)))

        if class_path:
            flags.extend(['-cp', safe_str.join(uniques(class_path),
                                               os.pathsep)])
        return flags

    def default_name(self, input, step):
        return input.path.stripext().suffix

    def output_file(self, name, step):
        return ObjectFileList(Path(name + '.classlist'), Path(name + '.class'),
                              self.builder.object_format, self.lang)


class JarMaker(BuildCommand):
    def __init__(self, builder, env, name, command, jarflags_name, jarflags):
        super().__init__(builder, env, 'jar', 'jar', command,
                         flags=(jarflags_name, jarflags))

    @property
    def flavor(self):
        return 'jar'

    def can_link(self, format, langs):
        return format == 'jvm'

    @property
    def needs_libs(self):
        return False

    def pre_build(self, context, name, step):
        # Fix up paths for the Class-Path field: escape spaces and prefix
        # Windows drive letters with '/' to disambiguate them from URLs.
        def fix_path(p):
            if self.env.target_platform.family == 'windows' and p[1] == ':':
                p = '/' + p
            return p.replace(' ', '%20')

        libs = getattr(step, 'libs', []) + flatten(
            i.libs for i in getattr(step, 'packages', [])
        )
        dirs = uniques(i.path for i in libs)
        base = Path(name).parent()

        step.manifest = File(Path(name + '-manifest.txt'))
        with make_immediate_file(context, step.manifest) as out:
            classpath = ' '.join(fix_path(i.relpath(base, localize=False))
                                 for i in dirs)
            if classpath:
                out.write('Class-Path: {}\n'.format(classpath))

            if getattr(step, 'entry_point', None):
                out.write('Main-Class: {}\n'.format(step.entry_point))

        return opts.option_list()

    def _call(self, cmd, input, output, manifest, flags=None):
        return list(chain(
            cmd, iterate(flags), [output, manifest], iterate(input)
        ))

    def transform_input(self, input):
        return ['@' + safe_str.safe_str(i) if isinstance(i, ObjectFileList)
                else i for i in input]

    def flags(self, options, output=None, mode='normal'):
        flags = []
        for i in options:
            if isinstance(i, safe_str.stringy_types):
                flags.append(i)
            elif isinstance(i, opts.debug):
                pass
            elif isinstance(i, opts.optimize):
                pass
            else:
                raise TypeError('unknown option type {!r}'.format(type(i)))
        return flags

    def output_file(self, name, step):
        if getattr(step, 'entry_point', None):
            filetype = ExecutableLibrary
        else:
            filetype = Library
        return filetype(Path(name + '.jar'), self.builder.object_format,
                        self.lang)


class JvmPackage(Package):
    def __init__(self, name, format, libs=None):
        super().__init__(name, format)
        self.libs = libs or []

    def compile_options(self, compiler):
        return opts.option_list(opts.lib(i) for i in self.libs)

    def link_options(self, linker):
        return opts.option_list()


class JvmPackageResolver:
    def __init__(self, builder, env, command):
        self.builder = builder

        if self.lang == 'scala':
            extra_env = {'JAVA_OPTS': '-XshowSettings:properties'}
            args = ['-version']
            returncode = 1
        else:
            extra_env = None
            args = ['-XshowSettings:properties', '-version']
            returncode = 0

        try:
            output = env.execute(
                command + args, env=extra_env, stdout=shell.Mode.devnull,
                stderr=shell.Mode.pipe, returncode=returncode
            )
            self.ext_dirs = self._get_dirs('java.ext.dirs', output)
            self.classpath = self._get_dirs('java.class.path', output)
        except (OSError, shell.CalledProcessError):
            self.ext_dirs = []
            self.classpath = []

    @property
    def lang(self):
        return self.builder.lang

    def _get_dirs(self, key, output):
        ex = r'^(\s*){} = (.*(?:\n\1\s+.*)*)'.format(re.escape(key))
        m = re.search(ex, output, re.MULTILINE)
        if not m:
            return []
        return [i.strip() for i in m.group(2).split('\n')]

    def _library(self, name):
        jarname = name + '.jar'
        for base in self.ext_dirs:
            fullpath = os.path.join(base, jarname)
            if os.path.exists(fullpath):
                return Library(Path(fullpath, Root.absolute),
                               self.builder.object_format)

        for path in self.classpath:
            if os.path.basename(path) == jarname and os.path.exists(path):
                return Library(Path(path, Root.absolute),
                               self.builder.object_format)

        raise PackageResolutionError("unable to find library '{}'"
                                     .format(name))

    def resolve(self, name, submodules, version, kind):
        lib = self._library(name)
        log.info('found package {!r} via path-search in {!r}'
                 .format(name, lib.path.parent().string()))
        return JvmPackage(name, self.builder.object_format, libs=[lib])


class JvmRunner(BuildCommand):
    def __init__(self, builder, env, name, command):
        super().__init__(builder, env, name, name, command)

    def _call(self, cmd, file, cp=None, jar=False):
        result = list(cmd)
        if jar and self.lang != 'scala':
            result.append('-jar')
        if not_buildroot(cp):
            result.extend(['-cp', cp])
        result.append(file)
        return result

    def run_arguments(self, file):
        if isinstance(file, Executable):
            return self(file, jar=True)
        elif isinstance(file, ObjectFileList):
            return self.run_arguments(file.object_file)
        elif isinstance(file, ObjectFile):
            return self(file.path.stripext().basename(), cp=file.path.parent())
        raise TypeError('expected an executable or object file for {} to run'
                        .format(self.lang))
