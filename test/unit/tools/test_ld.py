from unittest import mock

from .. import *

from bfg9000.tools.ld import LdLinker
from bfg9000.path import abspath
from bfg9000.versioning import Version


def mock_execute(args, **kwargs):
    return 'SEARCH_DIR("/dir1")\nSEARCH_DIR("=/dir2")\n'


class TestLdLinker(CrossPlatformTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(clear_variables=True, *args, **kwargs)

    def test_flavor(self):
        ld = LdLinker(None, self.env, ['ld'], 'version')
        self.assertEqual(ld.flavor, 'ld')

    def test_lang(self):
        class MockBuilder:
            lang = 'c++'

        ld = LdLinker(MockBuilder(), self.env, ['ld'], 'version')
        self.assertEqual(ld.lang, 'c++')

    def test_family(self):
        class MockBuilder:
            family = 'native'

        ld = LdLinker(MockBuilder(), self.env, ['ld'], 'version')
        self.assertEqual(ld.family, 'native')

    def test_gnu_ld(self):
        version = 'GNU ld (GNU Binutils for Ubuntu) 2.26.1'
        ld = LdLinker(None, self.env, ['ld'], version)

        self.assertEqual(ld.brand, 'bfd')
        self.assertEqual(ld.version, Version('2.26.1'))

    def test_gnu_gold(self):
        version = 'GNU gold (GNU Binutils for Ubuntu 2.26.1) 1.11'
        ld = LdLinker(None, self.env, ['ld'], version)

        self.assertEqual(ld.brand, 'gold')
        self.assertEqual(ld.version, Version('1.11'))

    def test_unknown_brand(self):
        version = 'unknown'
        ld = LdLinker(None, self.env, ['ld'], version)

        self.assertEqual(ld.brand, 'unknown')
        self.assertEqual(ld.version, None)

    def test_search_dirs(self):
        with mock.patch('bfg9000.shell.execute', mock_execute):
            ld = LdLinker(None, self.env, ['ld'], 'version')
            self.assertEqual(ld.search_dirs(),
                             [abspath('/dir1'), abspath('/dir2')])

    def test_search_dirs_sysroot(self):
        with mock.patch('bfg9000.shell.execute', mock_execute):
            ld = LdLinker(None, self.env, ['ld'], 'version')
            self.assertEqual(ld.search_dirs(sysroot='/sysroot'),
                             [abspath('/dir1'), abspath('/sysroot/dir2')])

    def test_search_dirs_fail(self):
        def mock_bad_execute(*args, **kwargs):
            raise OSError()

        with mock.patch('bfg9000.shell.execute', mock_bad_execute):
            ld = LdLinker(None, self.env, ['ld'], 'version')
            self.assertEqual(ld.search_dirs(), [])
            self.assertRaises(OSError, lambda: ld.search_dirs(strict=True))
