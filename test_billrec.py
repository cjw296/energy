from datetime import date
from decimal import Decimal
from functools import partial

from pandas import DataFrame, NaT, Timestamp
from testfixtures import ShouldRaise, compare as compare_

from billrec import (
    Charge, Rec, SheetBill, charges_from_transactions, format_rec, reconcile, sheet_bills, status
)

compare = partial(compare_, strict=True)

NAN = float('nan')


def charge(start: str, end: str, kwh: str = '10', cost_inc_vat: str = '5', standing_ex_vat: str = '1',
           usage_ex_vat: str = '0') -> Charge:
    return Charge(
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        kwh=Decimal(kwh),
        cost_inc_vat=Decimal(cost_inc_vat),
        standing_ex_vat=Decimal(standing_ex_vat),
        usage_ex_vat=Decimal(usage_ex_vat),
    )


def bill(end: str, kwh: float = 10.0, cost_inc_vat: float = 5.0,
         standing_ex_vat: float | None = 1.0) -> SheetBill:
    return SheetBill(end=date.fromisoformat(end), kwh=kwh, cost_inc_vat=cost_inc_vat,
                     standing_ex_vat=standing_ex_vat)


def consumption(start: str = '2026-07-15', end: str = '2026-08-31', quantity: str = '123.4560',
                usage_cost: int = 210, supply_charge: int = 105, unit: str = 'kWh') -> dict:
    return {'startDate': start, 'endDate': end, 'quantity': quantity, 'unit': unit,
            'usageCost': usage_cost, 'supplyCharge': supply_charge}


def transaction(**overrides) -> dict:
    node = {
        '__typename': 'Charge', 'postedDate': '2026-08-31', 'title': 'Electricity',
        'isReversed': False, 'isExport': False,
        'amounts': {'net': 100, 'tax': 5, 'gross': 105},
        'consumption': consumption(),
    }
    node.update(overrides)
    return node


def test_charges_from_transactions():
    transactions = [
        transaction(),
        transaction(isReversed=True),
        transaction(isExport=True),
        transaction(consumption=None),
        transaction(consumption=consumption(unit='MJ')),
        {'__typename': 'Payment', 'postedDate': '2026-09-17', 'title': 'Direct debit',
         'isReversed': False, 'amounts': {'net': -4321, 'tax': 0, 'gross': -4321}},
    ]
    compare(charges_from_transactions(transactions), expected=[
        charge('2026-07-15', '2026-08-31', kwh='123.4560', cost_inc_vat='1.05', standing_ex_vat='1',
               usage_ex_vat='2'),
    ])


def test_charges_sorted_by_end():
    transactions = [
        transaction(),
        transaction(consumption=consumption(start='2026-07-01', end='2026-07-14', quantity='10',
                                            usage_cost=105)),
    ]
    compare(charges_from_transactions(transactions), expected=[
        charge('2026-07-01', '2026-07-14', kwh='10', cost_inc_vat='1.05', standing_ex_vat='1',
               usage_ex_vat='1'),
        charge('2026-07-15', '2026-08-31', kwh='123.4560', cost_inc_vat='1.05', standing_ex_vat='1',
               usage_ex_vat='2'),
    ])


def test_zero_totals_raise():
    with ShouldRaise(ValueError(
        "zeros are bad: total_pence_inc_vat=Decimal('0'), total_pence_ex_vat=Decimal('0')"
    )):
        charges_from_transactions([transaction(amounts={'net': 0, 'tax': 0, 'gross': 0})])
    with ShouldRaise(ValueError(
        "zeros are bad: total_pence_inc_vat=Decimal('5'), total_pence_ex_vat=Decimal('0')"
    )):
        charges_from_transactions([transaction(amounts={'net': 0, 'tax': 5, 'gross': 5})])


def test_sheet_bills():
    sheet = DataFrame({
        'Date': [Timestamp('2025-10-31'), Timestamp('2025-11-30'), Timestamp('2025-11-02'),
                 Timestamp('2025-12-31'), Timestamp('2026-01-10'), NaT],
        'kwh': [500.5, 600.25, 50.75, 700.1, NAN, NAN],
        'Cost inc VAT': [50.01, 60.02, NAN, 70.03, NAN, 1.0],
        'Standing Charge (ex VAT)': [10.01, 10.02, NAN, NAN, NAN, NAN],
    })
    compare(sheet_bills(sheet), expected=[
        bill('2025-10-31', kwh=500.5, cost_inc_vat=50.01, standing_ex_vat=10.01),
        bill('2025-11-30', kwh=651.0, cost_inc_vat=60.02, standing_ex_vat=10.02),
        bill('2025-12-31', kwh=700.1, cost_inc_vat=70.03, standing_ex_vat=None),
    ])


def test_reconcile_one_to_one():
    compare(reconcile([bill('2026-07-14'), bill('2026-08-31')],
                      [charge('2026-07-15', '2026-08-31'), charge('2026-07-01', '2026-07-14')]),
            expected=[
                Rec(bill=bill('2026-07-14'), charges=[charge('2026-07-01', '2026-07-14')]),
                Rec(bill=bill('2026-08-31'), charges=[charge('2026-07-15', '2026-08-31')]),
            ])


def test_reconcile_many_charges_to_one_bill():
    compare(reconcile([bill('2025-03-10')],
                      [charge('2025-01-01', '2025-01-31'), charge('2025-02-01', '2025-03-10')]),
            expected=[
                Rec(bill=bill('2025-03-10'), charges=[charge('2025-01-01', '2025-01-31'),
                                                      charge('2025-02-01', '2025-03-10')]),
            ])


def test_reconcile_skips_bills_before_first_charge_and_reports_gaps():
    compare(reconcile([bill('2017-11-16'), bill('2019-10-04'), bill('2019-11-01'), bill('2019-11-30')],
                      [charge('2019-09-25', '2019-10-03'), charge('2019-12-01', '2019-12-31')]),
            expected=[
                Rec(bill=bill('2019-10-04'), charges=[charge('2019-09-25', '2019-10-03')]),
                Rec(bill=bill('2019-11-01'), charges=[]),
                Rec(bill=bill('2019-11-30'), charges=[]),
                Rec(bill=None, charges=[charge('2019-12-01', '2019-12-31')]),
            ])


def test_reconcile_no_charges():
    compare(reconcile([bill('2026-08-31')], []), expected=[])


def test_rec_totals():
    rec = Rec(bill=bill('2025-03-10'), charges=[
        charge('2025-01-01', '2025-01-31', kwh='1.5', cost_inc_vat='2.25', standing_ex_vat='0.5'),
        charge('2025-02-01', '2025-03-10', kwh='2.5', cost_inc_vat='1.25', standing_ex_vat='0.25'),
    ])
    compare((rec.kwh, rec.cost_inc_vat, rec.standing_ex_vat), expected=(4.0, 3.5, 0.75))


def test_status():
    matched = [charge('2026-07-15', '2026-08-31', kwh='123.456', cost_inc_vat='43.21', standing_ex_vat='12.346')]
    close = bill('2026-08-31', kwh=123.5, cost_inc_vat=43.21, standing_ex_vat=12.35)
    off = bill('2026-08-31', kwh=130.0, cost_inc_vat=43.00, standing_ex_vat=12.00)
    no_standing = bill('2026-08-31', kwh=123.5, cost_inc_vat=43.21, standing_ex_vat=None)
    compare(status(Rec(bill=close, charges=matched)), expected='ok')
    compare(status(Rec(bill=off, charges=matched)), expected='kWh, cost, standing')
    compare(status(Rec(bill=no_standing, charges=matched)), expected='ok')
    compare(status(Rec(bill=bill('2026-08-31'), charges=[])), expected='no api charges')
    compare(status(Rec(bill=None, charges=matched)), expected='not in sheet')


def test_format_rec():
    rec = Rec(
        bill=bill('2026-08-31', kwh=123.5, cost_inc_vat=43.21, standing_ex_vat=12.35),
        charges=[charge('2026-07-15', '2026-08-31', kwh='123.456', cost_inc_vat='43.21',
                        standing_ex_vat='12.346')],
    )
    compare(format_rec(rec), expected=(
        '2026-08-31  2026-07-15..2026-08-31     123.5    123.5    43.21   43.21   12.35  12.35  ok'
    ))


def test_format_rec_not_in_sheet():
    rec = Rec(bill=None, charges=[
        charge('2026-09-01', '2026-09-30', kwh='100', cost_inc_vat='20', standing_ex_vat='15'),
    ])
    compare(format_rec(rec), expected=(
        '-           2026-09-01..2026-09-30         -    100.0        -   20.00       -  15.00  not in sheet'
    ))
