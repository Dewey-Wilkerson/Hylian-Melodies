"""installer/deps.py: distro detection, the capability checks (with a fake probe) and the printed command."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from installer import deps  # noqa: E402

OS = {
    'cachyos': 'NAME="CachyOS Linux"\nID=cachyos\nID_LIKE=arch\n',
    'debian13': 'PRETTY_NAME="Debian GNU/Linux 13 (trixie)"\nID=debian\nVERSION_ID="13"\n',
    'debian12': 'ID=debian\nVERSION_ID="12"\n',
    'ubuntu2404': 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID="24.04"\n',
    'ubuntu2604': 'ID=ubuntu\nID_LIKE=debian\nVERSION_ID="26.04"\n',
    'mint': 'ID=linuxmint\nID_LIKE="ubuntu debian"\nVERSION_ID="22"\n',
    'fedora': 'ID=fedora\nVERSION_ID=45\n',
    'tumbleweed': 'ID="opensuse-tumbleweed"\nID_LIKE="opensuse suse"\nVERSION_ID="20261112"\n',
    'void': '# comment\nID=void\n',
}


class Fake:
    """Everything is there except what `missing` names: commands, pkg-config modules, Python modules, 'cxx'."""

    def __init__(self, *missing):
        self.missing = set(missing)

    def cmd(self, name):
        return name not in self.missing

    def pc(self, module, minimum=None):
        return module not in self.missing

    def py(self, module):
        return module not in self.missing

    def cxx(self):
        return 'cxx' not in self.missing


def run(name, *missing, **kw):
    return deps.check(deps.parse_os_release(OS[name]), Fake(*missing), **kw)


class Deps(unittest.TestCase):
    def test_family(self):
        want = {'cachyos': 'arch', 'debian13': 'debian', 'ubuntu2404': 'debian', 'mint': 'debian', 'fedora': 'fedora',
                'tumbleweed': 'suse', 'void': None}
        for name, fam in want.items():
            self.assertEqual(deps.family(deps.parse_os_release(OS[name])), fam, name)

    def test_table_is_complete(self):
        keys = [n['key'] for n in deps.NEEDS]
        self.assertEqual(len(keys), len(set(keys)))
        for n in deps.NEEDS:
            for fam in deps.FAMILIES:
                self.assertTrue(n['packages'][fam], (n['key'], fam))
            self.assertIn(n['group'], ('build', 'ui', 'package'))
        self.assertEqual(set(deps.INSTALL), set(deps.FAMILIES))
        self.assertEqual(set(deps.PACKER), set(deps.FAMILIES))

    def test_nothing_missing(self):
        r = run('fedora')
        self.assertEqual((r['missing'], r['command'], r['notes']), ([], '', []))

    def test_commands(self):
        self.assertEqual(run('cachyos', 'ninja', 'sdl3')['command'], 'sudo pacman -S --needed ninja sdl3')
        self.assertEqual(run('debian13', 'ninja', 'libavcodec', 'cxx')['command'],
                         'sudo apt install ninja-build g++ libavformat-dev libavcodec-dev libavutil-dev libswscale-dev')
        self.assertEqual(run('fedora', 'vulkan', 'clang++')['command'],
                         'sudo dnf install clang vulkan-headers vulkan-loader-devel')
        r = run('tumbleweed', 'curses', 'libswscale', 'rpmbuild')
        self.assertEqual(r['missing'], ['curses', 'ffmpeg', 'packer'])
        self.assertEqual(r['command'], "sudo zypper install python3-curses 'pkgconfig(libavformat)' "
                         "'pkgconfig(libavcodec)' 'pkgconfig(libavutil)' 'pkgconfig(libswscale)' rpm-build")

    def test_packages_named_once(self):
        # make and the C++ headers both name gcc on Arch
        self.assertEqual(run('cachyos', 'make', 'cxx')['command'], 'sudo pacman -S --needed make gcc')

    def test_packer_per_family(self):
        self.assertEqual(run('debian13', 'rpmbuild', 'makepkg')['missing'], [])
        self.assertEqual(run('debian13', 'dpkg-deb')['missing'], ['packer'])
        self.assertEqual(run('cachyos', 'makepkg')['command'], 'sudo pacman -S --needed base-devel')

    def test_release_without_sdl3(self):
        for name, since in (('debian12', 'Debian 13'), ('ubuntu2404', 'Ubuntu 26.04')):
            r = run(name, 'sdl3', 'ninja')
            self.assertEqual(r['missing'], ['ninja', 'sdl3'])
            self.assertEqual(r['command'], 'sudo apt install ninja-build')  # (no command for a package that isn't there)
            self.assertIn(since, r['notes'][0])
        self.assertEqual(run('ubuntu2604', 'sdl3')['notes'], [])
        self.assertEqual(run('debian12')['notes'], [])  # (SDL3 built by hand is fine)

    def test_unknown_distro(self):
        r = run('void', 'ninja')
        self.assertEqual((r['family'], r['command'], r['missing']), (None, '', ['ninja']))
        self.assertTrue(r['notes'])

    def test_groups(self):
        self.assertEqual(run('fedora', 'magick', 'curses', groups=('build',))['missing'], [])

    def test_real_probe_runs(self):
        r = deps.check({})
        self.assertEqual(len(r['needs']), len(deps.NEEDS))


if __name__ == '__main__':
    unittest.main()
