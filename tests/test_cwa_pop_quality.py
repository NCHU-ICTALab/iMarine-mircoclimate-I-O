from kaohsiung_microclimate_lstm.src.cwa.cwa_pop_quality import parse_cwa_pop_value


def test_parse_zero_is_available():
    assert parse_cwa_pop_value("0")["available"] is True
    assert parse_cwa_pop_value("0")["normalized_value"] == 0.0
    assert parse_cwa_pop_value(0)["normalized_value"] == 0.0


def test_parse_percent_and_probability_values():
    assert parse_cwa_pop_value("20")["normalized_value"] == 0.2
    assert parse_cwa_pop_value(20)["normalized_value"] == 0.2
    assert parse_cwa_pop_value("100")["normalized_value"] == 1.0
    assert parse_cwa_pop_value(0.5)["normalized_value"] == 0.5
    assert parse_cwa_pop_value("0.5")["normalized_value"] == 0.5
    assert parse_cwa_pop_value("20%")["normalized_value"] == 0.2


def test_parse_missing_and_invalid_values():
    assert parse_cwa_pop_value(None)["parse_status"] == "not_available"
    assert parse_cwa_pop_value("")["parse_status"] == "missing_field"
    assert parse_cwa_pop_value("N/A")["parse_status"] == "parse_error"
    assert parse_cwa_pop_value(-1)["parse_status"] == "out_of_range"
    assert parse_cwa_pop_value(101)["parse_status"] == "out_of_range"
