import os.path

from . import *

is_mingw = (env.host_platform.family == 'windows' and
            env.builder('c++').flavor == 'cc')


@skip_if(is_mingw, 'no conan on mingw (yet)')
class TestConan(IntegrationTest):
    def __init__(self, *args, **kwargs):
        IntegrationTest.__init__(
            self, os.path.join(examples_dir, '13_conan'),
            *args, **kwargs
        )

    def test_build(self):
        self.build()
        self.assertOutput([executable('program')], '')
