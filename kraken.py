from argparse import ArgumentTypeError
from collections.abc import Iterable

import requests

KRAKEN_API = {
    'octopus': 'https://api.octopus.energy',
    'edf': 'https://api.edfgb-kraken.energy',
    'eon': 'https://api.eonnext-kraken.energy',
}


def parse_product(spec: str) -> tuple[str, str]:
    supplier, _, code = spec.partition(':')
    if supplier not in KRAKEN_API or not code:
        raise ArgumentTypeError(
            f'expected SUPPLIER:CODE with SUPPLIER one of {", ".join(KRAKEN_API)}, got {spec!r}'
        )
    return supplier, code


def product(supplier: str, code: str) -> dict:
    response = requests.get(f'{KRAKEN_API[supplier]}/v1/products/{code}/', timeout=30)
    response.raise_for_status()
    return response.json()


def regional_rates(product: dict, regions: Iterable[str] | None = None) -> dict[str, dict[str, float]]:
    """Direct-debit, inc-VAT unit rates and standing charge (pence) for each region."""
    rates = {}
    for group, tariffs in product.items():
        if not (group.endswith('_electricity_tariffs') and tariffs):
            continue
        for region in sorted(tariffs) if regions is None else regions:
            if region not in tariffs:
                continue
            terms = tariffs[region].get('direct_debit_monthly') or tariffs[region].get('varying') or {}
            rates[region] = {
                name.removesuffix('_inc_vat'): value
                for name, value in terms.items()
                if name.endswith('_inc_vat')
                and ('rate' in name or 'standing' in name)
                and isinstance(value, (int, float))
            }
    return rates
