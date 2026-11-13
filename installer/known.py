"""Known-good facts about the official files: SHA-256 hashes, sizes, title IDs and versions. Facts only, no content.

Each supported game version lists the SHA-256 of the ExeFS files after extraction (update merged), and a manifest
hash of the RomFS: SHA-256 over the sorted lines "<path>\\t<size>\\t<sha256>\\n" of every file (installer/nx.py
tree_manifest). The XCI itself is not hashed: its certificate area differs per cartridge.
"""

APP_TITLE = 0x01000B900D8B0000
PATCH_TITLE = 0x01000B900D8B0800
AOC_TITLES = (0x01000B900D8B1001, 0x01000B900D8B1002, 0x01000B900D8B1003, 0x01000B900D8B1004)

VERSIONS = {
    # display version: data
    '1.4.0': {
        'patch_version': 393216,
        'program_nca_sha256': {
            'base': '07b3ade9af38892c021ca3f92d3933a928bda6bce616b4f872737e1020069fb8',
            'patch': 'dceebfd87c55f2d08a05c86f4b41e129288ae29270a2bc02e199f1b2bd9bee33',
        },
        'exefs_sha256': {
            'main': 'c6d221748eaba4867892c4ab107ac34c306577ed9529b4fbc0db2553e921f5c9',
            'main.npdm': 'ff5f12cb56a7d8032997633224a3901c9e27bcf589628144c6db40a0de560408',
            'rtld': '6f48768b5ebd6b570a5f784c911fe09e904b806fc7e1f063a8110f2bcadabc61',
            'sdk': 'd3e7f5dd35e0aa618abddeb1b9f05b38c5a94e4788374b4444c32df057fb0f42',
            'subsdk0': '2c25fea28c5c019e72b59ee62ae539234ab92a8baf11f567bfe97c8390842de9',
            'subsdk1': '7505e7c1e0a11d2cfc7daa39f0aa4c51632ee2998baaf5d48b9d711d8d729026',
        },
        'main_build_id': '7179a4bd112b6c656c274987aca710b8',
        'romfs': {'files': 679, 'bytes': 1841886432,
                  'manifest_sha256': '5615b8f363d67b18afee52949d99933f20bf636424150456e2a403e396d4f566'},
        # AoC RomFS manifests are filled in when first verified (see OPEN-QUESTIONS); until then the cnmt hashes of
        # the NCAs (checked during extraction) are the integrity check for DLC.
        'aoc': {},
    },
}
SUPPORTED = sorted(VERSIONS)
