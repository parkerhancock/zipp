import io
import zipfile
import contextlib
import pathlib
import unittest
import string

from test.support import temp_dir


# Poor man's technique to consume a (smallish) iterable.
consume = tuple


# from jaraco.itertools 5.0
class jaraco:
    class itertools:
        class Counter:
            def __init__(self, i):
                self.count = 0
                self._orig_iter = iter(i)

            def __iter__(self):
                return self

            def __next__(self):
                result = next(self._orig_iter)
                self.count += 1
                return result


def add_dirs(zf):
    """
    Given a writable zip file zf, inject directory entries for
    any directories implied by the presence of children.
    """
    for name in zipfile.CompleteDirs._implied_dirs(zf.namelist()):
        zf.writestr(name, b"")
    return zf


def build_alpharep_fixture():
    """
    Create a zip file with this structure:

    .
    ├── a.txt
    ├── b
    │   ├── c.txt
    │   ├── d
    │   │   └── e.txt
    │   └── f.txt
    └── g
        └── h
            └── i.txt

    This fixture has the following key characteristics:

    - a file at the root (a)
    - a file two levels deep (b/d/e)
    - multiple files in a directory (b/c, b/f)
    - a directory containing only a directory (g/h)

    "alpha" because it uses alphabet
    "rep" because it's a representative example
    """
    data = io.BytesIO()
    zf = zipfile.ZipFile(data, "w")
    zf.writestr("a.txt", b"content of a")
    zf.writestr("b/c.txt", b"content of c")
    zf.writestr("b/d/e.txt", b"content of e")
    zf.writestr("b/f.txt", b"content of f")
    zf.writestr("g/h/i.txt", b"content of i")
    zf.filename = "alpharep.zip"
    return zf


class TestPath(unittest.TestCase):
    def setUp(self):
        self.fixtures = contextlib.ExitStack()
        self.addCleanup(self.fixtures.close)

    def zipfile_alpharep(self):
        with self.subTest():
            yield build_alpharep_fixture()
        with self.subTest():
            yield add_dirs(build_alpharep_fixture())

    def zipfile_ondisk(self):
        tmpdir = pathlib.Path(self.fixtures.enter_context(temp_dir()))
        for alpharep in self.zipfile_alpharep():
            buffer = alpharep.fp
            alpharep.close()
            path = tmpdir / alpharep.filename
            with path.open("wb") as strm:
                strm.write(buffer.getvalue())
            yield path

    def test_iterdir_and_types(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            assert root.is_dir()
            a, b, g = root.iterdir()
            assert a.is_file()
            assert b.is_dir()
            assert g.is_dir()
            c, f, d = b.iterdir()
            assert c.is_file() and f.is_file()
            e, = d.iterdir()
            assert e.is_file()
            h, = g.iterdir()
            i, = h.iterdir()
            assert i.is_file()

    def test_subdir_is_dir(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            assert (root / 'b').is_dir()
            assert (root / 'b/').is_dir()
            assert (root / 'g').is_dir()
            assert (root / 'g/').is_dir()

    def test_open(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            a, b, g = root.iterdir()
            with a.open() as strm:
                data = strm.read()
            assert data == "content of a"

    def test_read(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            a, b, g = root.iterdir()
            assert a.read_text() == "content of a"
            assert a.read_bytes() == b"content of a"

    def test_joinpath(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            a = root.joinpath("a")
            assert a.is_file()
            e = root.joinpath("b").joinpath("d").joinpath("e.txt")
            assert e.read_text() == "content of e"

    def test_traverse_truediv(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            a = root / "a"
            assert a.is_file()
            e = root / "b" / "d" / "e.txt"
            assert e.read_text() == "content of e"

    def test_pathlike_construction(self):
        """
        zipfile.Path should be constructable from a path-like object
        """
        for zipfile_ondisk in self.zipfile_ondisk():
            pathlike = pathlib.Path(str(zipfile_ondisk))
            zipfile.Path(pathlike)

    def test_traverse_pathlike(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            root / pathlib.Path("a")

    def test_parent(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            assert (root / 'a').parent.at == ''
            assert (root / 'a' / 'b').parent.at == 'a/'

    def test_dir_parent(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            assert (root / 'b').parent.at == ''
            assert (root / 'b/').parent.at == ''

    def test_missing_dir_parent(self):
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            assert (root / 'missing dir/').parent.at == ''

    def test_mutability(self):
        """
        If the underlying zipfile is changed, the Path object should
        reflect that change.
        """
        for alpharep in self.zipfile_alpharep():
            root = zipfile.Path(alpharep)
            a, b, g = root.iterdir()
            alpharep.writestr('foo.txt', 'foo')
            alpharep.writestr('bar/baz.txt', 'baz')
            assert any(
                child.name == 'foo.txt'
                for child in root.iterdir())
            assert (root / 'foo.txt').read_text() == 'foo'
            baz, = (root / 'bar').iterdir()
            assert baz.read_text() == 'baz'

    HUGE_ZIPFILE_NUM_ENTRIES = 2 ** 13

    def huge_zipfile(self):
        """Create a read-only zipfile with a huge number of entries entries."""
        strm = io.BytesIO()
        zf = zipfile.ZipFile(strm, "w")
        for entry in map(str, range(self.HUGE_ZIPFILE_NUM_ENTRIES)):
            zf.writestr(entry, entry)
        zf.mode = 'r'
        return zf

    def test_joinpath_constant_time(self):
        """
        Ensure joinpath on items in zipfile is linear time.
        """
        root = zipfile.Path(self.huge_zipfile())
        entries = jaraco.itertools.Counter(root.iterdir())
        for entry in entries:
            entry.joinpath('suffix')
        # Check the file iterated all items
        assert entries.count == self.HUGE_ZIPFILE_NUM_ENTRIES

    # @func_timeout.func_set_timeout(3)
    def test_implied_dirs_performance(self):
        data = ['/'.join(string.ascii_lowercase + str(n)) for n in range(10000)]
        zipfile.CompleteDirs._implied_dirs(data)
