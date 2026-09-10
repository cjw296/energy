from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from pandas import DataFrame, Timestamp, isna

KWH_TOLERANCE = 0.5
MONEY_TOLERANCE = 0.011

HEADER = (
    f"{'sheet end':10}  {'api period':22}  {'kWh':>8} {'api':>8}  {'£':>7} {'api':>7}  "
    f"{'SC £':>6} {'api':>6}  status"
)


@dataclass(frozen=True)
class Charge:
    start: date
    end: date
    kwh: Decimal
    cost_inc_vat: Decimal
    standing_ex_vat: Decimal


def charges_from_transactions(transactions: list[dict[str, Any]]) -> list[Charge]:
    charges = []
    for transaction in transactions:
        consumption = transaction.get('consumption')
        if (transaction['__typename'] != 'Charge' or transaction['isReversed']
                or transaction.get('isExport') or not consumption
                or consumption['unit'] != 'kWh'):
            continue
        amounts = transaction['amounts']
        standing = Decimal(consumption['supplyCharge'])
        if amounts['gross']:
            standing = standing * amounts['net'] / amounts['gross']
        charges.append(Charge(
            start=date.fromisoformat(consumption['startDate']),
            end=date.fromisoformat(consumption['endDate']),
            kwh=Decimal(consumption['quantity']),
            cost_inc_vat=Decimal(amounts['gross']) / 100,
            standing_ex_vat=standing / 100,
        ))
    return sorted(charges, key=lambda charge: charge.end)


@dataclass(frozen=True)
class SheetBill:
    end: date
    kwh: float
    cost_inc_vat: float
    standing_ex_vat: float | None


def sheet_bills(sheet: DataFrame) -> list[SheetBill]:
    """Bills from rows with a cost; kWh from reading-only rows is carried into the next bill."""
    bills = []
    carried_kwh = 0.0
    for row in sheet.dropna(subset=['Date']).sort_values('Date').to_dict('records'):
        kwh = 0.0 if isna(row['kwh']) else float(row['kwh'])
        if isna(row['Cost inc VAT']):
            carried_kwh += kwh
            continue
        standing = row['Standing Charge (ex VAT)']
        bills.append(SheetBill(
            end=Timestamp(row['Date']).date(),
            kwh=carried_kwh + kwh,
            cost_inc_vat=float(row['Cost inc VAT']),
            standing_ex_vat=None if isna(standing) else float(standing),
        ))
        carried_kwh = 0.0
    return bills


@dataclass
class Rec:
    bill: SheetBill | None
    charges: list[Charge] = field(default_factory=list)

    @property
    def kwh(self) -> float:
        return float(sum(charge.kwh for charge in self.charges))

    @property
    def cost_inc_vat(self) -> float:
        return float(sum(charge.cost_inc_vat for charge in self.charges))

    @property
    def standing_ex_vat(self) -> float:
        return float(sum(charge.standing_ex_vat for charge in self.charges))


def reconcile(bills: list[SheetBill], charges: list[Charge]) -> list[Rec]:
    """Match each bill to the charges ending after the previous bill and on or before it."""
    recs = []
    remaining = sorted(charges, key=lambda charge: charge.end)
    first_end = remaining[0].end if remaining else None
    for bill in sorted(bills, key=lambda bill: bill.end):
        matched = [charge for charge in remaining if charge.end <= bill.end]
        remaining = [charge for charge in remaining if charge.end > bill.end]
        if first_end is not None and bill.end >= first_end:
            recs.append(Rec(bill, matched))
    recs.extend(Rec(None, [charge]) for charge in remaining)
    return recs


def status(rec: Rec) -> str:
    if rec.bill is None:
        return 'not in sheet'
    if not rec.charges:
        return 'no api charges'
    problems = []
    if abs(rec.kwh - rec.bill.kwh) > KWH_TOLERANCE:
        problems.append('kWh')
    if abs(rec.cost_inc_vat - rec.bill.cost_inc_vat) > MONEY_TOLERANCE:
        problems.append('cost')
    standing = rec.bill.standing_ex_vat
    if standing is not None and abs(rec.standing_ex_vat - standing) > MONEY_TOLERANCE:
        problems.append('standing')
    return ', '.join(problems) or 'ok'


def _num(value: float | None, width: int, places: int) -> str:
    return f'{"-":>{width}}' if value is None else f'{value:{width}.{places}f}'


def format_rec(rec: Rec) -> str:
    bill = rec.bill
    charged = bool(rec.charges)
    period = f'{rec.charges[0].start}..{rec.charges[-1].end}' if charged else '-'
    return '  '.join((
        f'{str(bill.end) if bill else "-":10}',
        f'{period:22}',
        _num(bill.kwh if bill else None, 8, 1) + ' ' + _num(rec.kwh if charged else None, 8, 1),
        _num(bill.cost_inc_vat if bill else None, 7, 2) + ' '
        + _num(rec.cost_inc_vat if charged else None, 7, 2),
        _num(bill.standing_ex_vat if bill else None, 6, 2) + ' '
        + _num(rec.standing_ex_vat if charged else None, 6, 2),
        status(rec),
    ))
