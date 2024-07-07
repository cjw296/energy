import json
from zoneinfo import ZoneInfo

from pandas import Timestamp

from schedule import make_seasons_and_energy_charges
from testfixtures import compare, ShouldRaise, log_capture, LogCapture

London = ZoneInfo('Europe/London')


SAMPLE_UNIT_RATES_29_FEB = [
    {
        "value": 7.49994,
        "validTo": "2024-02-29T05:30:00+00:00",
        "validFrom": "2024-02-28T23:30:00+00:00"
    },
    {
        "value": 30.59805,
        "validTo": "2024-02-29T23:30:00+00:00",
        "validFrom": "2024-02-29T05:30:00+00:00"
    },
    {
        "value": 7.49994,
        "validTo": "2024-03-01T05:30:00+00:00",
        "validFrom": "2024-02-29T23:30:00+00:00"
    },
    {
        "value": 30.59805,
        "validTo": "2024-03-01T23:30:00+00:00",
        "validFrom": "2024-03-01T05:30:00+00:00"
    },
    {
        "value": 7.49994,
        "validTo": "2024-03-02T05:30:00+00:00",
        "validFrom": "2024-03-01T23:30:00+00:00"
    }
]


def expected_schedule(summer_tou_periods, rates: dict[str, float] | None = None):
    if rates is None:
        rates = {
            "ON_PEAK": 0.31,
            "SUPER_OFF_PEAK": 0.07
        }
    return {
        "energy_charges": {
            "ALL": {
                "ALL": 0
            },
            "Summer": rates,
            "Winter": {}
        },
        "seasons": {
            "Summer": {
                "fromDay": 1,
                "toDay": 31,
                "fromMonth": 1,
                "toMonth": 12,
                "tou_periods": summer_tou_periods
            },
            "Winter": {
                "fromDay": 0,
                "toDay": 0,
                "fromMonth": 0,
                "toMonth": 0,
                "tou_periods": {}
            }
        }
    }


BASIC_SCHEDULE = expected_schedule({
    "ON_PEAK": [
        {
            "fromDayOfWeek": 0,
            "toDayOfWeek": 6,
            "fromHour": 5,
            "fromMinute": 30,
            "toHour": 23,
            "toMinute": 30
        }
    ],
    "SUPER_OFF_PEAK": [
        {
            "fromDayOfWeek": 0,
            "toDayOfWeek": 6,
            "fromHour": 0,
            "fromMinute": 0,
            "toHour": 5,
            "toMinute": 30
        },
        {
            "fromDayOfWeek": 0,
            "toDayOfWeek": 6,
            "fromHour": 23,
            "fromMinute": 30,
            "toHour": 0,
            "toMinute": 0
        }
    ]
})


def test_no_dispatches():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-02-29T16:42:12', tz=London),
        unit_rates_schedule=SAMPLE_UNIT_RATES_29_FEB,
        dispatches={},
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)


def test_planned_dispatches_all_inside_cheap_window():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-02-29T16:42:12', tz=London),
        unit_rates_schedule=SAMPLE_UNIT_RATES_29_FEB,
        dispatches={
            "plannedDispatches": [
                {
                    "startDtUtc": "2024-02-29 23:30:00+00:00",
                    "endDtUtc": "2024-03-01 00:00:00+00:00",
                    "chargeKwh": "-1.71",
                    "meta": {
                        "source": "smart-charge",
                        "location": None
                    }
                },
                {
                    "startDtUtc": "2024-03-01 02:00:00+00:00",
                    "endDtUtc": "2024-03-01 02:30:00+00:00",
                    "chargeKwh": "-0.40",
                    "meta": {
                        "source": "smart-charge",
                        "location": None
                    }
                },
                {
                    "startDtUtc": "2024-03-01 02:30:00+00:00",
                    "endDtUtc": "2024-03-01 05:00:00+00:00",
                    "chargeKwh": "-8.55",
                    "meta": {
                        "source": "smart-charge",
                        "location": None
                    }
                }
            ],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)


def test_planned_dispatches_extend_cheap_window():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-02-29T21:48:00', tz=London),
        unit_rates_schedule=SAMPLE_UNIT_RATES_29_FEB,
        dispatches={
            "plannedDispatches": [
                {
                    "startDtUtc": "2024-02-29 21:47:30+00:00",
                    "endDtUtc": "2024-03-01 05:30:00+00:00",
                    "chargeKwh": "-26.38",
                    "meta": {
                        "source": "smart-charge",
                        "location": None
                    }
                }
            ],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(
        json.loads(json.dumps(actual)), expected=expected_schedule({
            "ON_PEAK": [
                {
                    "fromDayOfWeek": 0,
                    "toDayOfWeek": 6,
                    "fromHour": 5,
                    "fromMinute": 30,
                    "toHour": 21,
                    "toMinute": 30
                }
            ],
            "SUPER_OFF_PEAK": [
                {
                    "fromDayOfWeek": 0,
                    "toDayOfWeek": 6,
                    "fromHour": 0,
                    "fromMinute": 0,
                    "toHour": 5,
                    "toMinute": 30
                },
                {
                    "fromDayOfWeek": 0,
                    "toDayOfWeek": 6,
                    "fromHour": 21,
                    "fromMinute": 30,
                    "toHour": 0,
                    "toMinute": 0
                }
            ]
        })
    )


def test_planned_dispatch_is_not_smart_charge():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-02-29T21:48:00', tz=London),
        unit_rates_schedule=SAMPLE_UNIT_RATES_29_FEB,
        dispatches={
            "plannedDispatches": [
                {
                    "startDtUtc": "2024-02-29 21:47:30+00:00",
                    "endDtUtc": "2024-03-01 05:30:00+00:00",
                    "chargeKwh": "-26.38",
                    "meta": {
                        "source": "bump",
                        "location": None
                    }
                }
            ],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)


SHORT_UNIT_RATES_RESPONSE = [
        {
            "value": 7.49994,
            "validFrom": "2024-03-04T23:30:00+00:00",
            "validTo": "2024-03-05T05:30:00+00:00",
        },
        {
            "value": 30.59805,
            "validFrom": "2024-03-05T05:30:00+00:00",
            "validTo": "2024-03-05T23:30:00+00:00",
        },
        {
            "value": 7.49994,
            "validFrom": "2024-03-05T23:30:00+00:00",
            "validTo": "2024-03-06T05:30:00+00:00",
        }
    ]


def test_unit_rates_fall_a_bit_short():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-03-05T07:05:30', tz=London),
        unit_rates_schedule=SHORT_UNIT_RATES_RESPONSE,
        dispatches={
            "plannedDispatches": [],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)


@log_capture()
def test_unit_rates_fall_a_lot_short(logs: LogCapture):
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-03-05T09:54:41', tz=London),
        unit_rates_schedule=SHORT_UNIT_RATES_RESPONSE,
        dispatches={
            "plannedDispatches": [],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)
    logs.check()


@log_capture()
def test_unit_rates_fall_too_much_short(logs: LogCapture):
    actual = make_seasons_and_energy_charges(
            now=Timestamp('2024-03-05T11:00:30', tz=London),
            unit_rates_schedule=SHORT_UNIT_RATES_RESPONSE,
            dispatches={
                "plannedDispatches": [],
                "completedDispatches": []
            },
            timezone=London
        )
    compare(json.loads(json.dumps(actual)), expected=BASIC_SCHEDULE)
    logs.check(
        (
            'root',
            'WARNING',
            'Missing standard unit rates for 5.5 hours from 2024-03-06 05:30:00+00:00'
        ),
    )


CHANGING_UNIT_RATES_RESPONSE = [
        {
            "value": 7.49994,
            "validTo": "2024-06-30T04:30:00+00:00",
            "validFrom": "2024-06-29T22:30:00+00:00"
        },
        {
            "value": 27.274275,
            "validTo": "2024-06-30T22:30:00+00:00",
            "validFrom": "2024-06-30T04:30:00+00:00"
        },
        {
            "value": 7.49994,
            "validTo": "2024-06-30T23:00:00+00:00",
            "validFrom": "2024-06-30T22:30:00+00:00"
        },
        {
            "value": 6.00035,
            "validTo": "2024-07-01T04:30:00+00:00",
            "validFrom": "2024-06-30T23:00:00+00:00"
        },
        {
            "value": 23.7132,
            "validTo": "2024-07-01T22:30:00+00:00",
            "validFrom": "2024-07-01T04:30:00+00:00"
        },
        {
            "value": 6.00035,
            "validTo": "2024-07-02T04:30:00+00:00",
            "validFrom": "2024-07-01T22:30:00+00:00"
        }
    ]


CHANGING_RATES_SCHEDULE = expected_schedule(
    {
        "ON_PEAK": [
            {
                "fromDayOfWeek": 0,
                "toDayOfWeek": 6,
                "fromHour": 11  ,
                "fromMinute": 0,
                "toHour": 23,
                "toMinute": 30
            }
        ],
        "SUPER_OFF_PEAK": [
            {
                "fromDayOfWeek": 0,
                "toDayOfWeek": 6,
                "fromHour": 23,
                "fromMinute": 30,
                "toHour": 0,
                "toMinute": 0
            },
        ],
        "NEW_SUPER_OFF_PEAK": [
            {
                'fromDayOfWeek': 0,
                'fromHour': 0,
                'fromMinute': 0,
                'toDayOfWeek': 6,
                'toHour': 5,
                'toMinute': 30
            },
        ],
        "NEW_ON_PEAK": [
            {
                'fromDayOfWeek': 0,
                'fromHour': 5,
                'fromMinute': 30,
                'toDayOfWeek': 6,
                'toHour': 11,
                'toMinute': 0
            },
        ],
    },
    rates =  {
        "ON_PEAK": 0.27,
        "SUPER_OFF_PEAK": 0.07,
        "NEW_ON_PEAK": 0.24,
        "NEW_SUPER_OFF_PEAK": 0.06,
    }
)


def test_unit_rates_changing():
    actual = make_seasons_and_energy_charges(
        now=Timestamp('2024-06-30T11:05:26', tz=London),
        unit_rates_schedule=CHANGING_UNIT_RATES_RESPONSE,
        dispatches={
            "plannedDispatches": [],
            "completedDispatches": []
        },
        timezone=London
    )
    compare(json.loads(json.dumps(actual)), expected=CHANGING_RATES_SCHEDULE)
