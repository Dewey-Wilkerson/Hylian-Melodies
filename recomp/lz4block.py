"""LZ4 block decoder (the format NSO segments use), written for this project so no Python package is needed.

Format: a run of sequences, each a token (high nibble: literal count, low nibble: match length - 4; 15 means more
length bytes follow, each added until one is below 255), the literals, then a 2-byte little-endian match offset
back into the output. The last sequence ends after its literals.
"""


def decompress(src, uncompressed_size):
    src = bytes(src)
    n = len(src)
    out = bytearray()
    i = 0
    try:
        while i < n:
            token = src[i]
            i += 1
            lit = token >> 4
            if lit == 15:
                while True:
                    b = src[i]
                    i += 1
                    lit += b
                    if b != 255:
                        break
            if i + lit > n:
                raise ValueError('lz4: literals run past the input')
            out += src[i:i + lit]
            i += lit
            if i >= n:
                break
            offset = src[i] | src[i + 1] << 8
            i += 2
            length = token & 15
            if length == 15:
                while True:
                    b = src[i]
                    i += 1
                    length += b
                    if b != 255:
                        break
            length += 4
            start = len(out) - offset
            if offset == 0 or start < 0:
                raise ValueError('lz4: match offset outside the output')
            if offset >= length:
                out += out[start:start + length]
            else:  # the match overlaps what it writes: the last `offset` bytes repeat
                out += (bytes(out[start:]) * (length // offset + 1))[:length]
            if len(out) > uncompressed_size:
                raise ValueError('lz4: output larger than declared')
    except IndexError:
        raise ValueError('lz4: input ends inside a sequence') from None
    if len(out) != uncompressed_size:
        raise ValueError(f'lz4: got {len(out)} bytes, expected {uncompressed_size}')
    return bytes(out)
