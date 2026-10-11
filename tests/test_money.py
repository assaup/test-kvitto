import pytest

from app.money import (
    UnknownPromoCodeError,
    calculate_price,
    get_discount_percent,
    percent_of,
    split_into_installments,
)
from app.seed import DEFAULT_TARIFFS

TARIFF_PRICES = [price for _, _, price in DEFAULT_TARIFFS]


# --- Промокод ---


@pytest.mark.parametrize("code", ["KVITTO10", "kvitto10", "KvItTo10", "  kvitto10  "])
def test_promo_code_is_case_insensitive(code: str) -> None:
    assert get_discount_percent(code) == 10


@pytest.mark.parametrize("code", [None, "", "   "])
def test_missing_promo_code_gives_no_discount(code: str | None) -> None:
    assert get_discount_percent(code) == 0


@pytest.mark.parametrize(
    "code",
    [
        "KVITTO20",
        "KVITTO",
        "KVITTO100",
        "KVIT TO10",
        "kvıtto10",  # турецкая ı без точки: "ı".upper() == "I"
        "KVITTO１０",  # полноширинные цифры
    ],
)
def test_unknown_promo_code_is_rejected(code: str) -> None:
    with pytest.raises(UnknownPromoCodeError):
        get_discount_percent(code)


# --- Процент и округление ---


@pytest.mark.parametrize(
    ("amount", "percent", "expected"),
    [
        (990_000, 10, 99_000),
        (1_990_000, 10, 199_000),
        (2_990_000, 10, 299_000),
        (4, 10, 0),  # 0.4 коп. → 0
        (5, 10, 1),  # 0.5 коп. → 1 (половина вверх)
        (15, 10, 2),  # 1.5 коп. → 2
        (14, 10, 1),  # 1.4 коп. → 1
        (1_990_000, 0, 0),
        (1_990_000, 100, 1_990_000),
    ],
)
def test_percent_of_rounds_half_up(amount: int, percent: int, expected: int) -> None:
    assert percent_of(amount, percent) == expected


@pytest.mark.parametrize(("amount", "percent"), [(-1, 10), (100, -1), (100, 101)])
def test_percent_of_rejects_invalid_input(amount: int, percent: int) -> None:
    with pytest.raises(ValueError):
        percent_of(amount, percent)


# --- Цена с промокодом и без ---


@pytest.mark.parametrize(
    ("tariff_price", "promo_code", "expected_amount", "expected_discount"),
    [
        (990_000, None, 990_000, 0),
        (1_990_000, None, 1_990_000, 0),
        (2_990_000, None, 2_990_000, 0),
        (990_000, "kvitto10", 891_000, 99_000),
        (1_990_000, "kvitto10", 1_791_000, 199_000),
        (2_990_000, "KVITTO10", 2_691_000, 299_000),
    ],
)
def test_calculate_price(
    tariff_price: int, promo_code: str | None, expected_amount: int, expected_discount: int
) -> None:
    price = calculate_price(tariff_price, get_discount_percent(promo_code))

    assert price.amount == expected_amount
    assert price.discount == expected_discount
    assert price.amount + price.discount == tariff_price


@pytest.mark.parametrize("tariff_price", [1, 5, 15, 99_999, 1_234_567])
def test_calculate_price_never_loses_kopecks_on_odd_prices(tariff_price: int) -> None:
    price = calculate_price(tariff_price, 10)

    assert price.amount + price.discount == tariff_price


# --- График рассрочки ---


def test_installment_schedule_example_from_spec() -> None:
    assert split_into_installments(1_990_000, 3) == [663_334, 663_333, 663_333]


def test_extra_kopecks_go_to_first_payments() -> None:
    assert split_into_installments(2_990_000, 3) == [996_667, 996_667, 996_666]


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("discount_percent", [0, 10])
@pytest.mark.parametrize("tariff_price", TARIFF_PRICES)
def test_installment_schedule_sums_to_amount(
    tariff_price: int, discount_percent: int, months: int
) -> None:
    amount = calculate_price(tariff_price, discount_percent).amount

    schedule = split_into_installments(amount, months)

    assert sum(schedule) == amount
    assert len(schedule) == months
    assert all(type(payment) is int for payment in schedule)
    assert max(schedule) - min(schedule) <= 1  # платежи отличаются максимум на копейку
    assert schedule == sorted(schedule, reverse=True)  # лишние копейки — в первых платежах


@pytest.mark.parametrize(("amount", "months"), [(100, 0), (100, -3), (2, 3), (0, 3)])
def test_split_rejects_invalid_input(amount: int, months: int) -> None:
    with pytest.raises(ValueError):
        split_into_installments(amount, months)
