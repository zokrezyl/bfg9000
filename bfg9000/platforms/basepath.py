import ntpath
import os
import posixpath
from enum import Enum
from itertools import chain

from .. import safe_str
from ..objutils import objectify

Root = Enum('Root', ['srcdir', 'builddir', 'absolute'])
InstallRoot = Enum('InstallRoot', ['prefix', 'exec_prefix', 'bindir', 'libdir',
                                   'includedir'])
DestDir = Enum('DestDir', ['destdir'])


class BasePath(safe_str.safe_string):
    __slots__ = ['destdir', 'root', 'suffix']

    curdir = posixpath.curdir
    pardir = posixpath.pardir
    sep = posixpath.sep

    __repr_variables = dict(
        [(i, '$({})'.format(i.name)) for i in chain(Root, InstallRoot)] +
        [(DestDir.destdir, '$(DESTDIR)')]
    )

    def __init__(self, path, root=Root.builddir, destdir=False):
        if destdir and root in Root:
            raise ValueError('destdir only applies to install paths')
        drive, path = self.__normalize(path, expand_user=True)

        if posixpath.isabs(path):
            root = Root.absolute
            destdir = False
        elif root == Root.absolute:
            raise ValueError("'{}' is not absolute".format(path))
        elif isinstance(root, BasePath):
            path = self.__join(root.suffix, path)
            destdir = root.destdir
            root = root.root

        if ( path == posixpath.pardir or
             path.startswith(posixpath.pardir + posixpath.sep) ):
            raise ValueError("too many '..': path cannot escape root")

        self.suffix = drive + path
        self.root = root
        self.destdir = destdir

    @classmethod
    def abspath(cls, path):
        drive, path = cls.__normalize(path, expand_user=True)
        cwddrive, cwdpath = cls.__normalize(os.getcwd())

        if not drive:
            drive = cwddrive
        path = cls.__join(cwdpath, path)
        return cls(drive + path, Root.absolute)

    @classmethod
    def ensure(cls, path, root=Root.builddir, destdir=False, base=None,
               strict=False):
        result = objectify(path, base or cls, cls, root=root, destdir=destdir)
        if strict and result.root != root:
            raise ValueError('expected root of {!r}, but got {!r}'
                             .format(root.name, result.root.name))
        return result

    @staticmethod
    def __normalize(path, expand_user=False):
        if expand_user:
            path = os.path.expanduser(path)
        drive, path = ntpath.splitdrive(path)
        if drive and not ntpath.isabs(path):
            raise ValueError('relative paths with drives not supported')

        drive = drive.replace('\\', '/')
        path = posixpath.normpath(path.replace('\\', '/'))
        if path == posixpath.curdir:
            path = ''
        return drive, path

    @staticmethod
    def __join(path1, path2):
        path = posixpath.normpath(posixpath.join(path1, path2))
        return '' if path == posixpath.curdir else path

    def __localize(self, thing):
        if isinstance(thing, str):
            return self._localize_path(thing)
        return thing

    def cross(self, env):
        cls = env.target_platform.Path
        return cls(self.suffix, self.root)

    def parent(self):
        if not self.suffix:
            raise ValueError('already at root')
        return type(self)(posixpath.dirname(self.suffix), self.root,
                          self.destdir)

    def append(self, path):
        drive, path = self.__normalize(path, expand_user=True)
        if not posixpath.isabs(path):
            path = self.__join(self.suffix, path)
        return type(self)(drive + path, self.root, self.destdir)

    def ext(self):
        return posixpath.splitext(self.suffix)[1]

    def addext(self, ext):
        return type(self)(self.suffix + ext, self.root, self.destdir)

    def stripext(self, replace=None):
        name = posixpath.splitext(self.suffix)[0]
        if replace:
            name += replace
        return type(self)(name, self.root, self.destdir)

    def splitleaf(self):
        return self.parent(), self.basename()

    def split(self):
        # This is guaranteed to work since `suffix` is normalized.
        return self.suffix.split(posixpath.sep)

    def basename(self):
        return posixpath.basename(self.suffix)

    def relpath(self, start, prefix=''):
        if self.root == Root.absolute:
            return self.__localize(self.suffix)
        if self.root != start.root:
            raise ValueError('source mismatch')

        rel = posixpath.relpath(self.suffix or posixpath.curdir,
                                start.suffix or posixpath.curdir)
        if prefix and rel == self.curdir:
            return prefix
        return self.__localize(posixpath.join(prefix, rel))

    def reroot(self, root=Root.builddir):
        return type(self)(self.suffix, root, self.destdir)

    def to_json(self):
        return (self.suffix, self.root.name, self.destdir)

    @classmethod
    def from_json(cls, data):
        try:
            base = Root[data[1]]
        except KeyError:
            base = InstallRoot[data[1]]
        return cls(data[0], base, data[2])

    def realize(self, variables, executable=False):
        root = variables[self.root] if self.root != Root.absolute else None
        if executable and root is None and posixpath.sep not in self.suffix:
            root = posixpath.curdir

        # Not all platforms (e.g. Windows) support $(DESTDIR), so only emit the
        # destdir variable if it's defined.
        if self.destdir and DestDir.destdir in variables:
            root = variables[DestDir.destdir] + root
        if root is None:
            return self.__localize(self.suffix or posixpath.curdir)
        if not self.suffix:
            return self.__localize(root)

        # Join the separator and the suffix first so that we don't end up with
        # unnecessarily-escaped backslashes on Windows. (It doesn't hurt
        # anything; it just looks weird.)
        return (self.__localize(root) +
                self.__localize(posixpath.sep + self.suffix))

    def string(self, variables=None):
        path = self
        result = ''

        while True:
            real = path.realize(variables)
            if isinstance(real, safe_str.jbos):
                path, suffix = real.bits
                result = suffix + result
            elif isinstance(real, BasePath):
                path = real
            else:
                result = real + result
                break

        return result

    def __str__(self):
        raise NotImplementedError()

    def __repr__(self):
        return '`{}`'.format(self.realize(self.__repr_variables))

    def __hash__(self):
        return hash(self.suffix)

    def __eq__(self, rhs):
        if type(self) is not type(rhs):
            return NotImplemented
        return (self.root == rhs.root and self.suffix == rhs.suffix and
                self.destdir == rhs.destdir)

    def __ne__(self, rhs):
        return not (self == rhs)
