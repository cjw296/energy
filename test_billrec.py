from datetime import date
from decimal import Decimal
from functools import partial

from pandas import DataFrame, NaT, Timestamp
from testfixtures import compare as compare_

from billrec import (
    Charge, Rec, SheetBill, charges_from_transactions, format_rec, reconcile, sheet_bills, status
)

compare = partial(compare_, strict=True)

NAN = float('nan')


def charge(start: str, end: str, kwh: str = '10', cost: str = '5', standing: str = '1') -> Charge:
    return Charge(date.fromisoformat(start), date.fromisoformat(end),
                  Decimal(kwh), Decimal(cost), Decimal(standing))


def bill(end: str, kwh: float = 10.0, cost: float = 5.0, standing: float | None = 1.0) -> SheetBill:
    return SheetBill(date.fromisoformat(end), kwh, cost, standing)


def transaction(**overrides):
    node = {
        '__typename': 'Charge', 'postedDate': '2026-08-31', 'title': 'Electricity',
        'isReversed': False, 'isExport': False,
        'amounts': {'net': 100, 'tax': 5, 'gross': 105},
        'consumption': {'startDate': '2026-07-15', 'endDate': '2026-08-31', 'quantity': '123.4560',
                        'unit': 'kWh', 'usageCost': 0, 'supplyCharge': 105},
    }
    node.update(overrides)
    return node


def test_charges_from_transactions():
    transactions = [
        transaction(),
        transaction(isReversed=True),
        transaction(isExport=True),
        transaction(consumption=None),
        transaction(consumption={'startDate': '2026-07-15', 'endDate': '2026-08-31', 'quantity': '5',
                                 'unit': 'MJ', 'usageCost': 0, 'supplyCharge': 0}),
        {'__typename': 'Payment', 'postedDate': '2026-09-17', 'title': 'Direct debit',
         'isReversed': False, 'amounts': {'net': -4321, 'tax': 0, 'gross': -4321}},
    ]
    compare(charges_from_transactions(transactions), expected=[
        Charge(date(2026, 7, 15), date(2026, 8, 31), Decimal('123.4560'), Decimal('1.05'), Decimal('1')),
    ])


def test_charges_sorted_by_end_and_zero_gross():
    transactions = [
        transaction(),
        transaction(amounts={'net': 0, 'tax': 0, 'gross': 0},
                    consumption={'startDate': '2026-07-01', 'endDate': '2026-07-14', 'quantity': '0',
                                 'unit': 'kWh', 'usageCost': 0, 'supplyCharge': 0}),
    ]
    compare(charges_from_transactions(transactions), expected=[
        Charge(date(2026, 7, 1), date(2026, 7, 14), Decimal('0'), Decimal('0'), Decimal('0')),
        Charge(date(2026, 7, 15), date(2026, 8, 31), Decimal('123.4560'), Decimal('1.05'), Decimal('1')),
    ])


def test_sheet_bills():
    sheet = DataFrame({
        'Date': [Timestamp('2025-10-31'), Timestamp('2025-11-30'), Timestamp('2025-11-02'),
                 Timestamp('2025-12-31'), Timestamp('2026-01-10'), NaT],
        'kwh': [500.5, 600.25, 50.75, 700.1, NAN, NAN],
        'Cost inc VAT': [50.01, 60.02, NAN, 70.03, NAN, 1.0],
        'Standing Charge (ex VAT)': [10.01, 10.02, NAN, NAN, NAN, NAN],
    })
    compare(sheet_bills(sheet), expected=[
        SheetBill(date(2025, 10, 31), 500.5, 50.01, 10.01),
        SheetBill(date(2025, 11, 30), 651.0, 60.02, 10.02),
        SheetBill(date(2025, 12, 31), 700.1, 70.03, None),
    ])


def test_reconcile_one_to_one():
    compare(reconcile([bill('2026-07-14'), bill('2026-08-31')],
                      [charge('2026-07-15', '2026-08-31'), charge('2026-07-01', '2026-07-14')]),
            expected=[
                Rec(bill('2026-07-14'), [charge('2026-07-01', '2026-07-14')]),
                Rec(bill('2026-08-31'), [charge('2026-07-15', '2026-08-31')]),
            ])


def test_reconcile_many_charges_to_one_bill():
    compare(reconcile([bill('2025-03-10')],
                      [charge('2025-01-01', '2025-01-31'), charge('2025-02-01', '2025-03-10')]),
            expected=[
                Rec(bill('2025-03-10'), [charge('2025-01-01', '2025-01-31'),
                                         charge('2025-02-01', '2025-03-10')]),
            ])


def test_reconcile_skips_bills_before_first_charge_and_reports_gaps():
    compare(reconcile([bill('2017-11-16'), bill('2019-10-04'), bill('2019-11-01'), bill('2019-11-30')],
                      [charge('2019-09-25', '2019-10-03'), charge('2019-12-01', '2019-12-31')]),
            expected=[
                Rec(bill('2019-10-04'), [charge('2019-09-25', '2019-10-03')]),
                Rec(bill('2019-11-01'), []),
                Rec(bill('2019-11-30'), []),
                Rec(None, [charge('2019-12-01', '2019-12-31')]),
            ])


def test_reconcile_no_charges():
    compare(reconcile([bill('2026-08-31')], []), expected=[])


def test_rec_totals():
    rec = Rec(bill('2025-03-10'), [charge('2025-01-01', '2025-01-31', '1.5', '2.25', '0.5'),
                                   charge('2025-02-01', '2025-03-10', '2.5', '1.25', '0.25')])
    compare((rec.kwh, rec.cost_inc_vat, rec.standing_ex_vat), expected=(4.0, 3.5, 0.75))


def test_status():
    matched = [charge('2026-07-15', '2026-08-31', '123.456', '43.21', '12.346')]
    compare(status(Rec(bill('2026-08-31', 123.5, 43.21, 12.35), matched)), expected='ok')
    compare(status(Rec(bill('2026-08-31', 130.0, 43.00, 12.00), matched)),
            expected='kWh, cost, standing')
    compare(status(Rec(bill('2026-08-31', 123.5, 43.21, None), matched)), expected='ok')
    compare(status(Rec(bill('2026-08-31'), [])), expected='no api charges')
    compare(status(Rec(None, matched)), expected='not in sheet')


def test_format_rec():
    rec = Rec(bill('2026-08-31', 123.5, 43.21, 12.35),
              [charge('2026-07-15', '2026-08-31', '123.456', '43.21', '12.346')])
    compare(format_rec(rec), expected=(
        '2026-08-31  2026-07-15..2026-08-31     123.5    123.5    43.21   43.21   12.35  12.35  ok'
    ))


def test_format_rec_not_in_sheet():
    rec = Rec(None, [charge('2026-09-01', '2026-09-30', '100', '20', '15')])
    compare(format_rec(rec), expected=(
        '-           2026-09-01..2026-09-30         -    100.0        -   20.00       -  15.00  not in sheet'
    ))
