import pytest

from services.enrollment import EnrollmentError, _validate_student_fields


def test_rejects_blank_roll_no():
    with pytest.raises(EnrollmentError):
        _validate_student_fields("", "Alice", 1, 1)


def test_rejects_blank_name():
    with pytest.raises(EnrollmentError):
        _validate_student_fields("21CE001", "  ", 1, 1)


def test_rejects_out_of_range_year():
    with pytest.raises(EnrollmentError):
        _validate_student_fields("21CE001", "Alice", 99, 1)


def test_rejects_out_of_range_semester():
    with pytest.raises(EnrollmentError):
        _validate_student_fields("21CE001", "Alice", 1, 99)


def test_accepts_valid_fields():
    _validate_student_fields("21CE001", "Alice", 2, 4)  # should not raise


def test_accepts_none_year_semester():
    _validate_student_fields("21CE001", "Alice", None, None)  # should not raise
