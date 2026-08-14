from gpu_cabt.rng import bounded_u32, philox_u32, philox4x32_10, shuffle_in_place


def test_philox4x32_10_standard_zero_vector() -> None:
    assert philox4x32_10((0, 0, 0, 0), (0, 0)) == (
        0x6627E8D5,
        0xE169C58D,
        0xBC57AC4C,
        0x9B00DBD8,
    )


def test_philox_u32_exposes_block_lanes() -> None:
    expected = (0x6627E8D5, 0xE169C58D, 0xBC57AC4C, 0x9B00DBD8)
    assert tuple(philox_u32(0, 0, index) for index in range(4)) == expected


def test_bounded_u32_is_in_range_and_advances() -> None:
    draw_index = 0
    values: list[int] = []
    for _ in range(1000):
        value, next_draw_index = bounded_u32(1234, 9876, draw_index, 17)
        assert 0 <= value < 17
        assert next_draw_index > draw_index
        values.append(value)
        draw_index = next_draw_index
    assert len(set(values)) == 17


def test_shuffle_is_deterministic_permutation_and_stream_separated() -> None:
    first = list(range(60))
    second = list(range(60))
    other_stream = list(range(60))
    draws_first = shuffle_in_place(first, seed=123, stream=456)
    draws_second = shuffle_in_place(second, seed=123, stream=456)
    shuffle_in_place(other_stream, seed=123, stream=457)
    assert first == second
    assert first != other_stream
    assert sorted(first) == list(range(60))
    assert draws_first == draws_second
    assert draws_first >= 59


def test_shuffle_can_continue_from_existing_rng_cursor() -> None:
    first = list(range(8))
    second = list(range(8))
    next_index = shuffle_in_place(first, seed=99, stream=7, draw_index=13)
    repeated_next = shuffle_in_place(second, seed=99, stream=7, draw_index=13)
    assert first == second
    assert next_index == repeated_next
    assert next_index >= 20
