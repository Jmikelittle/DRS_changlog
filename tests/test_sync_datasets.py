from sync_datasets import is_insignificant_change


def test_blank_to_zero_is_ignored():
    assert is_insignificant_change('', '0') is True
    assert is_insignificant_change('', 0) is True
    assert is_insignificant_change('0', '') is True


def test_decimal_only_numeric_change_is_ignored():
    assert is_insignificant_change('242.0', '242') is True
    assert is_insignificant_change('0.00', '0') is True


def test_real_value_change_is_not_ignored():
    assert is_insignificant_change('242', '243') is False
    assert is_insignificant_change('active', 'inactive') is False
