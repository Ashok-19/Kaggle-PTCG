from __future__ import annotations

from collections.abc import MutableSequence

_U32_MASK = 0xFFFFFFFF
_U64_MASK = 0xFFFFFFFFFFFFFFFF
_M0 = 0xD2511F53
_M1 = 0xCD9E8D57
_W0 = 0x9E3779B9
_W1 = 0xBB67AE85


def _u32(value: int) -> int:
    return value & _U32_MASK


def _mulhilo32(a: int, b: int) -> tuple[int, int]:
    product = (a & _U32_MASK) * (b & _U32_MASK)
    return (product >> 32) & _U32_MASK, product & _U32_MASK


def philox4x32_10(
    counter: tuple[int, int, int, int], key: tuple[int, int]
) -> tuple[int, int, int, int]:
    """Portable Philox4x32-10 reference used by CPU/GPU differential tests."""

    c0, c1, c2, c3 = (_u32(value) for value in counter)
    k0, k1 = (_u32(value) for value in key)
    for round_index in range(10):
        hi0, lo0 = _mulhilo32(_M0, c0)
        hi1, lo1 = _mulhilo32(_M1, c2)
        c0, c1, c2, c3 = (
            _u32(hi1 ^ c1 ^ k0),
            lo1,
            _u32(hi0 ^ c3 ^ k1),
            lo0,
        )
        if round_index != 9:
            k0 = _u32(k0 + _W0)
            k1 = _u32(k1 + _W1)
    return c0, c1, c2, c3


def philox_u32(seed: int, stream: int, draw_index: int) -> int:
    """Return one deterministic uint32 from a seed/stream/draw coordinate."""

    if draw_index < 0:
        raise ValueError("draw_index must be nonnegative")
    seed &= _U64_MASK
    stream &= _U64_MASK
    block = draw_index >> 2
    lane = draw_index & 3
    values = philox4x32_10(
        (
            block & _U32_MASK,
            (block >> 32) & _U32_MASK,
            stream & _U32_MASK,
            (stream >> 32) & _U32_MASK,
        ),
        (seed & _U32_MASK, (seed >> 32) & _U32_MASK),
    )
    return values[lane]


def bounded_u32(seed: int, stream: int, draw_index: int, bound: int) -> tuple[int, int]:
    """Unbiased Lemire bounded draw, returning ``(value, next_draw_index)``."""

    if not 1 <= bound <= _U32_MASK:
        raise ValueError("bound must be in [1, 2**32-1]")
    threshold = ((1 << 32) - bound) % bound
    while True:
        value = philox_u32(seed, stream, draw_index)
        draw_index += 1
        product = value * bound
        low = product & _U32_MASK
        if low >= threshold:
            return (product >> 32) & _U32_MASK, draw_index


def shuffle_in_place(
    values: MutableSequence[int], *, seed: int, stream: int, draw_index: int = 0
) -> int:
    """Deterministic Fisher-Yates shuffle; return the next RNG draw index."""

    if draw_index < 0:
        raise ValueError("draw_index must be nonnegative")
    for index in range(len(values) - 1, 0, -1):
        swap_index, draw_index = bounded_u32(seed, stream, draw_index, index + 1)
        values[index], values[swap_index] = values[swap_index], values[index]
    return draw_index
