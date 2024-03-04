import json
from zoneinfo import ZoneInfo

from pandas import Timestamp

from schedule import make_seasons_and_energy_charges
from test_octopus import compare

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


def expected_schedule(summer_tou_periods):
    return {
        "energy_charges": {
            "ALL": {
                "ALL": 0
            },
            "Summer": {
                "ON_PEAK": 0.31,
                "SUPER_OFF_PEAK": 0.07
            },
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

