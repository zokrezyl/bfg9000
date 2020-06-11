import json
import os
import yaml

from . import tool
from .common import SimpleCommand
from .. import shell
from ..iterutils import iterate
from ..packages import Framework
from ..path import Path, Root
from ..safe_str import safe_format


@tool('mopack')
class Mopack(SimpleCommand):
    package_dir = Path('mopack')

    def __init__(self, env):
        super().__init__(env, name='mopack', env_var='MOPACK',
                         default='mopack')

    def _dir_arg(self, directory):
        return ['--directory', directory] if directory else []

    def _call_resolve(self, cmd, config, *, directory=None):
        result = cmd + ['resolve']
        result.extend(iterate(config))
        result.extend(self._dir_arg(directory))

        for k, v in self.env.install_dirs.items():
            if v is not None and v.root == Root.absolute:
                result.append(safe_format('-P{}={}', k.name, v))

        return result

    def _call_usage(self, cmd, name, submodules=None, *, directory=None):
        result = cmd + ['usage', '--json', name]
        result.extend(safe_format('-s{}', i) for i in iterate(submodules))
        result.extend(self._dir_arg(directory))
        return result

    def _call_deploy(self, cmd, *, directory=None):
        return cmd + ['deploy'] + self._dir_arg(directory)

    def _call_clean(self, cmd, *, directory=None):
        return cmd + ['clean'] + self._dir_arg(directory)

    def _call(self, cmd, subcmd, *args, **kwargs):
        return getattr(self, '_call_' + subcmd)(cmd, *args, **kwargs)

    def run(self, subcmd, *args, **kwargs):
        result = super().run(subcmd, *args, **kwargs)
        if subcmd == 'usage':
            return json.loads(result.strip())
        return result


def try_usage(env, name, submodules=None):
    try:
        return env.tool('mopack').run(
            'usage', name, submodules, directory=env.builddir
        )
    except (OSError, shell.CalledProcessError):
        return {'name': name, 'type': 'system', 'headers': [],
                'libraries': [name]}


def to_frameworks(libs):
    def convert(lib):
        if isinstance(lib, dict):
            if lib['type'] == 'framework':
                return Framework(lib['name'])
            raise ValueError('unknown type {!r}'.format(lib['type']))
        return lib

    return [convert(i) for i in libs]


def _dump_yaml(data):
    # `sort_keys` only works on newer versions of PyYAML, so don't worry too
    # much if we can't use it.
    try:
        return yaml.dump(data, sort_keys=False)
    except TypeError:
        return yaml.dump(data)


def make_mopack_options_yml(env):
    options = {}
    if env.target_platform != env.host_platform:
        options['target_platform'] = env.target_platform.name
    if env.variables.changes:
        options['env'] = env.variables.changes
    if env.toolchain.path:
        options['builders'] = {'bfg9000': {
            'toolchain': env.toolchain.path.string()
        }}

    path = Path('mopack-options.yml')
    if options:
        with open(path.string(env.base_dirs), 'w') as f:
            print(_dump_yaml({'options': options}), file=f)
        return path
    else:
        try:
            os.remove(path.string(env.base_dirs))
        except FileNotFoundError:
            pass
