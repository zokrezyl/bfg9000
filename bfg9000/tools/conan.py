from . import tool
from .common import SimpleCommand


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
