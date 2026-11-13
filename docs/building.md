# Building (development)

Requirements (Arch names): `base-devel git python python-lz4 clang lld llvm ninja sdl3 vulkan-headers
vulkan-icd-loader opus libvpx zstd ffmpeg`. Exact versions on the dev machine: `DEV-ENVIRONMENT.md`.

```bash
git config core.hooksPath .githooks
python3 -m unittest discover -s tests
python3 tools/build_hactool.py --src ~/.cache/hylian-melodies/toolchain/src/hactool \
                               --out ~/.cache/hylian-melodies/toolchain/hactool
python3 -m installer --base cadence-base.xci --keys prod.keys --dest ~/.cache/hylian-melodies/dev \
    --temp ~/.cache/hylian-melodies/temp --hactool ~/.cache/hylian-melodies/toolchain/hactool/hactool --until extract
```

Game-dependent tests: `HM_TEST_XCI=... HM_TEST_KEYS=... HM_TEST_HACTOOL=... python3 -m unittest tests.test_installer`.
