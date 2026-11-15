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

    def clang_major(self):
        return 0 if 'clang' in self.missing else 14 if 'clang17' in self.missing else 19


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
            for fam in deps.FAMILIES:  # (the SDL3 build is only needed, and only tried, on old Debian-family releases)
                self.assertTrue(n['packages'][fam] or (n['key'] == 'sdl3-headers' and fam != 'debian'), (n['key'], fam))
            self.assertIn(n['group'], ('build', 'ui', 'package', 'sdl3-own', 'own'))
        self.assertEqual(set(deps.INSTALL), set(deps.FAMILIES))
        self.assertEqual(set(deps.PACKER), set(deps.FAMILIES))

    def test_nothing_missing(self):
        r = run('fedora')
        self.assertEqual((r['missing'], r['command'], r['notes']), ([], '', []))
        self.assertEqual((r['sdl3'], r['shaderc']), ('system', 'system'))

    def test_commands(self):
        self.assertEqual(run('cachyos', 'ninja', 'sdl3')['command'], 'sudo pacman -S --needed ninja sdl3')
        self.assertEqual(run('debian13', 'ninja', 'libavcodec', 'cxx')['command'],
                         'sudo apt install ninja-build g++ libavformat-dev libavcodec-dev libavutil-dev libswscale-dev')
        self.assertEqual(run('fedora', 'vulkan', 'clang')['command'],
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

    def test_release_without_sdl3_builds_its_own(self):
        r = run('ubuntu2404', 'sdl3', 'cmake', 'xtst')
        self.assertEqual((r['sdl3'], r['shaderc']), ('own', 'system'))
        self.assertEqual(r['missing'], ['cmake', 'sdl3-headers'])  # (no 'sdl3': there is no package to ask for)
        self.assertTrue(r['command'].startswith('sudo apt install cmake libwayland-dev '))
        self.assertNotIn('libsdl3-dev', r['command'])
        self.assertIn('Ubuntu 26.04', r['notes'][0])
        r = run('ubuntu2404', 'sdl3')  # everything for the build is there
        self.assertEqual((r['sdl3'], r['missing'], r['command']), ('own', [], ''))
        # an SDL3 the player installed themself is used as it is; a release that has the package is asked for it
        self.assertEqual(run('ubuntu2404')['sdl3'], 'system')
        r = run('ubuntu2604', 'sdl3')
        self.assertEqual((r['sdl3'], r['command'], r['notes']), ('system', 'sudo apt install libsdl3-dev', []))

    def test_debian12_builds_shaderc_and_names_clang19(self):
        r = run('debian12', 'sdl3', 'shaderc', 'clang', 'ld.lld', 'cmake')
        self.assertEqual((r['sdl3'], r['shaderc']), ('own', 'own'))
        self.assertEqual(r['missing'], ['clang', 'lld', 'cmake'])  # (neither sdl3 nor shaderc: no package to ask for)
        self.assertEqual(r['command'], 'sudo apt install clang-19 lld-19 cmake')
        self.assertIn('shaderc', r['notes'][-1])
        r = run('debian13', 'clang')
        self.assertEqual((r['shaderc'], r['command']), ('system', 'sudo apt install clang'))

    def test_newer_clang_dir(self):
        import tempfile
        with tempfile.TemporaryDirectory() as root:
            for n in ('llvm-14', 'llvm-19', 'llvm-22', 'llvm-x', 'llvm-30'):
                os.makedirs(os.path.join(root, n, 'bin'))
            for n in ('llvm-14', 'llvm-19', 'llvm-22'):  # (llvm-30 has no clang in it)
                open(os.path.join(root, n, 'bin', 'clang'), 'w').close()
            self.assertEqual(deps.newer_clang_dir(root), os.path.join(root, 'llvm-22', 'bin'))
            os.remove(os.path.join(root, 'llvm-22', 'bin', 'clang'))
            os.remove(os.path.join(root, 'llvm-19', 'bin', 'clang'))
            self.assertIsNone(deps.newer_clang_dir(root))  # (14 is too old)
        self.assertIsNone(deps.newer_clang_dir('/nonexistent'))

    def test_clang_version(self):
        r = run('ubuntu2404', 'clang17')
        self.assertEqual(r['missing'], ['clang'])
        self.assertIn('version 14', r['notes'][-1])

    def test_either_imagemagick_command(self):
        self.assertEqual(run('ubuntu2404', 'magick')['missing'], [])  # (ImageMagick 6 has only `convert`)
        self.assertEqual(run('ubuntu2404', 'magick', 'convert')['missing'], ['magick'])

    def test_unknown_distro(self):
        r = run('void', 'ninja')
        self.assertEqual((r['family'], r['command'], r['missing']), (None, '', ['ninja']))
        self.assertTrue(r['notes'])

    def test_groups(self):
        self.assertEqual(run('fedora', 'magick', 'curses', groups=('build',))['missing'], [])

    def test_real_probe_runs(self):
        r = deps.check({})
        self.assertEqual(len(r['needs']), len([n for n in deps.NEEDS if n['group'] not in ('sdl3-own', 'own')]))


if __name__ == '__main__':
    unittest.main()
