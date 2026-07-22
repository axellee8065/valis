import pytest

from packages.adapter_kr.molit.xml_parser import (
    MolitApiError,
    MolitParseError,
    parse_apt_trade_response,
)


def test_parse_normal_response(molit_fixture):
    page = parse_apt_trade_response(molit_fixture("apt_trade_11680_202401.xml"))
    assert page.total_count == 2
    assert len(page.items) == 2

    first = page.items[0]
    assert first.sgg_cd == "11680"
    assert first.umd_nm == "역삼동"
    assert first.apt_nm == "역삼래미안"
    assert first.deal_amount == "125,000"
    assert first.exclu_use_ar == "84.99"
    assert first.cdeal_type == ""
    assert first.raw["estateAgentSggNm"] == "서울 강남구"


def test_parse_cancelled_response(molit_fixture):
    page = parse_apt_trade_response(molit_fixture("apt_trade_cancelled.xml"))
    item = page.items[0]
    assert item.cdeal_type == "O"
    assert item.cdeal_day == "24.01.20"
    assert item.dealing_gbn == "직거래"


def test_parse_empty_response(molit_fixture):
    page = parse_apt_trade_response(molit_fixture("apt_trade_empty.xml"))
    assert page.items == []
    assert page.total_count == 0


def test_api_error_raises(molit_fixture):
    with pytest.raises(MolitApiError) as exc_info:
        parse_apt_trade_response(molit_fixture("apt_trade_error.xml"))
    assert exc_info.value.result_code == "22"


def test_malformed_xml_raises(molit_fixture):
    with pytest.raises(MolitParseError):
        parse_apt_trade_response(molit_fixture("apt_trade_malformed.xml"))
