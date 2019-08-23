from . import tool
from .common import SimpleCommand


def parse_build_info(file, section):
    result = []
    in_section = False

    for line in file:
        line = line.rstrip('\n')
        if not line:
            continue
        elif line[0] == '[':
            if line[-1] != ']':
                raise ValueError("expected ']' at end of line")
            if len(line) == 2:
                raise ValueError('expected section name')
            if in_section:
                break
            in_section = section == line[1:-1]
        elif in_section:
            result.append(line)

    return result


@tool('conan')
class Conan(SimpleCommand):
    def __init__(self, env):
        SimpleCommand.__init__(self, env, name='conan', env_var='CONAN',
                               default='conan')

    def _call(self, cmd, generator, srcdir, builddir, arch=None):
        result = cmd + ['install', '-g', generator]
        if arch:
            result.extend(['-s', 'arch=' + arch])
        if builddir:
            result.extend(['-if', builddir])
        result.append(srcdir)

        return result
