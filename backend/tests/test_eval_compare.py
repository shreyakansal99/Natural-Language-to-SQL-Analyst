from eval.run_eval import compare


def test_ignores_row_and_column_order():
    assert compare([[1, "a"], [2, "b"]], [["b", 2], ["a", 1]]) == "exact"


def test_numbers_compare_within_tolerance_and_int_equals_float():
    assert compare([[10.04]], [[10.0]]) == "exact"
    assert compare([[5]], [[5.0]]) == "exact"
    assert compare([[1000.0]], [[1004.0]]) == "exact"    # within 1%
    assert compare([[1000.0]], [[1100.0]]) is None       # 10% off


def test_small_values_use_absolute_tolerance():
    assert compare([[0.50]], [[0.505]]) == "exact"
    assert compare([[0.50]], [[0.60]]) is None


def test_extra_columns_are_accepted_and_labelled():
    assert compare([[1], [2]], [["x", 1], ["y", 2]]) == "extra_columns"


def test_wrong_values_and_wrong_row_counts_fail():
    assert compare([[1]], [[2]]) is None
    assert compare([[1], [2]], [[1]]) is None


def test_ordered_flag():
    assert compare([[1], [2]], [[2], [1]], ordered=True) is None
    assert compare([[1], [2]], [[2], [1]]) == "exact"