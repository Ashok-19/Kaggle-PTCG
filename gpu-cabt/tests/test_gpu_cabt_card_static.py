import pytest

from gpu_cabt.card_static import SetupCardStatic, dense_setup_card_table


def test_dense_setup_card_table_is_directly_indexed() -> None:
    records = [
        SetupCardStatic(2, True, False, True, True),
        SetupCardStatic(5, False, True, True, True),
    ]
    payload, rows = dense_setup_card_table(records)
    assert rows == 6
    assert len(payload) == 24
    assert payload[2 * 4 : 3 * 4] == bytes((1, 0, 1, 1))
    assert payload[5 * 4 : 6 * 4] == bytes((0, 1, 1, 1))
    assert payload[3 * 4 : 4 * 4] == bytes(4)


def test_dense_setup_card_table_rejects_duplicates() -> None:
    records = [
        SetupCardStatic(2, True, False, True, True),
        SetupCardStatic(2, False, False, False, False),
    ]
    with pytest.raises(ValueError, match="duplicate"):
        dense_setup_card_table(records)
