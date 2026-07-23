"""Contract tests for the AE (Dubai DLD) normalizer.

The canonical ID assertions here are a contract: if any of these change,
every AE global_id changes and on-chain attestation links break.
"""

from datetime import date
from decimal import Decimal

import pytest

from packages.adapter_ae.dld.normalizer import (
    AED_USD_PEG,
    RawDldTransaction,
    bedroom_code,
    canonical_local_id,
    slugify,
    source_record_id,
    to_property,
    to_transaction,
)
from packages.core.schemas import PropertyType, TransactionType


def make_raw(**overrides) -> RawDldTransaction:
    base = dict(
        procedure_name="Sell",
        instance_date="15-03-2024",
        property_type="Unit",
        property_sub_type="Flat",
        property_usage="Residential",
        area_name="Burj Khalifa",
        building_name="Burj Vista 1",
        master_project="Downtown Dubai",
        bedrooms="2 B/R",
        parkings="1",
        built_up_area_sqft="1190.0",
        selling_price_aed="3500000.0",
        raw={},
    )
    base.update(overrides)
    return RawDldTransaction(**base)


class TestSlugify:
    def test_basic(self):
        assert slugify("Burj Khalifa") == "BURJ-KHALIFA"

    def test_punctuation_and_runs(self):
        assert slugify("Al Khairan (First) — Tower A/2") == "AL-KHAIRAN-FIRST-TOWER-A-2"

    def test_unicode_stripped(self):
        assert slugify("Café Tower") == "CAFE-TOWER"

    def test_empty(self):
        assert slugify("") == ""


class TestBedroomCode:
    @pytest.mark.parametrize(
        ("label", "code"),
        [
            ("Studio", "0BR"),
            ("1 B/R", "1BR"),
            ("2 B/R", "2BR"),
            ("10 B/R", "10BR"),
            ("PENTHOUSE", "PH"),
            ("Single Room", "SR"),
            ("Shop", "X"),
            ("", "X"),
        ],
    )
    def test_mapping(self, label, code):
        assert bedroom_code(label) == code


class TestCanonicalId:
    def test_contract_example(self):
        # 1190 sqft → 110.55 sqm → 11055
        raw = make_raw()
        assert canonical_local_id(raw) == "AE-DXB-BURJ-KHALIFA-BURJ-VISTA-1-2BR-11055"

    def test_source_record_id(self):
        raw = make_raw()
        assert (
            source_record_id(raw) == "AE-DXB-BURJ-KHALIFA-BURJ-VISTA-1-2BR-11055@20240315#3500000"
        )


class TestToTransaction:
    def test_sale(self):
        tx = to_transaction(make_raw())
        assert tx.transaction_type is TransactionType.SALE
        assert tx.transaction_date == date(2024, 3, 15)
        assert tx.price_original_currency == "AED"
        assert tx.price_original_amount == Decimal("3500000.0")
        # 3.5M AED / 3.6725 = $953,029.27
        assert tx.price_usd_cents == 95302927
        assert tx.fx_rate_at_date == AED_USD_PEG
        assert tx.global_id.startswith("0x")

    def test_offplan_procedure(self):
        tx = to_transaction(make_raw(procedure_name="Sell - Pre registration"))
        assert tx.transaction_type is TransactionType.SALE

    def test_unknown_procedure_raises(self):
        with pytest.raises(KeyError):
            to_transaction(make_raw(procedure_name="Mortgage Registration"))


class TestToProperty:
    def test_fields(self):
        prop = to_property(make_raw())
        assert prop.country_code == "AE"
        assert prop.property_type is PropertyType.APARTMENT
        assert prop.admin_level_1 == "Dubai"
        assert prop.admin_level_2 == "Burj Khalifa"
        assert prop.net_area_sqm == Decimal("110.55")
        assert prop.complex_name == "Burj Vista 1"
        assert prop.community_name == "Downtown Dubai"
        assert prop.is_offplan is False

    def test_offplan_flag(self):
        prop = to_property(make_raw(procedure_name="Sell - Pre registration"))
        assert prop.is_offplan is True

    def test_same_class_same_global_id(self):
        a = to_property(make_raw(selling_price_aed="2000000"))
        b = to_property(make_raw(selling_price_aed="9000000"))
        assert a.global_id == b.global_id
