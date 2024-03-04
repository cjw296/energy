from datetime import time, datetime
from functools import partial
from zoneinfo import ZoneInfo

import pytest
from pandas import Timestamp
from pytz.exceptions import NonExistentTimeError
from testfixtures import compare as compare_, ShouldRaise, ShouldAssert

compare = partial(compare_, strict=True)


from octopus import Schedule, ScheduleEntry, TimeSlot


def ts(time: str, date: str = "2024-02-18", tz: str | ZoneInfo='+00:00') -> Timestamp:
    if time.count(':') < 2:
        time += ':00'
    return Timestamp(f'{date}T{time}', tz=tz)


def test_simple():
    schedule = Schedule(ts("05:55:23", date="2024-02-18"))
    schedule.add(ts("05:31:01", date='2024-02-18'), ts("05:29:59", date='2024-02-19'), 10)
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("05:30", date='2024-02-18'), ts("05:30", date='2024-02-19'), 10)
    ])


def test_multiple():
    schedule = Schedule(ts("00:00"))
    schedule.add(ts("00:00"), ts("05:00"), 5)
    schedule.add(ts("05:00"), ts("11:30"), 10)
    schedule.add(ts("11:30"), ts("23:30"), 10)
    schedule.add(ts("23:30"), ts("00:00", date='2024-02-19'), 5)
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("00:00", date='2024-02-18'), ts("05:00", date='2024-02-18'), 5),
        ScheduleEntry(ts("05:00", date='2024-02-18'), ts("23:30", date='2024-02-18'), 10),
        ScheduleEntry(ts("23:30", date='2024-02-18'), ts("00:00", date='2024-02-19'), 5),
    ])


def test_overwrite():
    schedule = Schedule(ts("00:00"))
    schedule.add(ts("00:00"), ts("00:00", date='2024-02-19'), 20)
    schedule.add(ts("10:01"), ts("11:29"), 5)
    schedule.add(ts("23:00"), ts("23:30"), 10)
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("00:00", date='2024-02-18'), ts("10:00", date='2024-02-18'), 20),
        ScheduleEntry(ts("10:00", date='2024-02-18'), ts("11:30", date='2024-02-18'), 5),
        ScheduleEntry(ts("11:30", date='2024-02-18'), ts("23:00", date='2024-02-18'), 20),
        ScheduleEntry(ts("23:00", date='2024-02-18'), ts("23:30", date='2024-02-18'), 10),
        ScheduleEntry(ts("23:30", date='2024-02-18'), ts("00:00", date='2024-02-19'), 20),
    ])


def test_gaps():
    schedule = Schedule(ts("00:00"))
    schedule.add(ts("00:30"), ts("10:00"), 10)
    schedule.add(ts("11:00"), ts("23:00"), 20)
    with ShouldRaise(ValueError(
            "Gaps in schedule: ['2024-02-18 00:00:00+00:00', '2024-02-18 10:00:00+00:00', "
            "'2024-02-18 10:30:00+00:00', '2024-02-18 23:00:00+00:00', '2024-02-18 23:30:00+00:00']")
    ):
        schedule.final()


def test_real_world():
    schedule = Schedule(Timestamp("2024-02-20T10:11:48+00:00"))
    schedule.add(
        start=Timestamp("2024-02-19T23:30:00+00:00"),
        end=Timestamp("2024-02-20T05:30:00+00:00"),
        cost=7.49994,
    )
    schedule.add(
        start=Timestamp("2024-02-20T05:30:00+00:00"),
        end=Timestamp("2024-02-20T23:30:00+00:00"),
        cost=30.59805,
    )
    schedule.add(
        start=Timestamp("2024-02-20T23:30:00+00:00"),
        end=Timestamp("2024-02-21T05:30:00+00:00"),
        cost=7.49994,
    )
    schedule.add(
        start=Timestamp("2024-02-21T05:30:00+00:00"),
        end=Timestamp("2024-02-21T23:30:00+00:00"),
        cost=30.59805,
    )
    schedule.add(
        start=Timestamp("2024-02-21T23:30:00+00:00"),
        end=Timestamp("2024-02-22T05:30:00+00:00"),
        cost=7.49994,
    )
    compare(schedule.final(), expected=[
        ScheduleEntry(start=Timestamp('2024-02-20 10:00:00+0000', tz='UTC'),
                      end=Timestamp('2024-02-20 23:30:00+0000', tz='UTC'),
                      cost=30.59805),
        ScheduleEntry(start=Timestamp('2024-02-20 23:30:00+0000', tz='UTC'),
                      end=Timestamp('2024-02-21 05:30:00+0000', tz='UTC'),
                      cost=7.49994),
        ScheduleEntry(start=Timestamp('2024-02-21 05:30:00+0000', tz='UTC'),
                      end=Timestamp('2024-02-21 10:00:00+0000', tz='UTC'),
                      cost=30.59805)
    ])


def test_ends_before_schedule_day_starts():
    schedule = Schedule(ts("00:00", date='2024-02-20'))
    # This one is ignored:
    schedule.add(ts("12:00", date='2024-02-19'), ts("00:00", date='2024-02-20'), 10)
    schedule.add(ts("00:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20)
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("00:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20),
    ])


def test_starts_after_schedule_day_ends():
    schedule = Schedule(ts("00:00", date='2024-02-20'))
    schedule.add(ts("00:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20)
    # This one is ignored:
    schedule.add(ts("00:00", date='2024-02-21'), ts("12:00", date='2024-02-21'), 10)
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("00:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20),
    ])


def test_add_in_other_timezone():
    schedule = Schedule(ts("00:00", date='2024-02-20'))
    schedule.add(ts("00:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20)

    schedule.add(
        ts("12:00", date='2024-02-20', tz=ZoneInfo('Europe/Berlin')),
        ts("13:00", date='2024-02-20', tz=ZoneInfo('Europe/Berlin')),
        10
    )
    compare(schedule.final(), expected=[
        ScheduleEntry(ts("00:00", date='2024-02-20'), ts("11:00", date='2024-02-20'), 20),
        ScheduleEntry(ts("11:00", date='2024-02-20'), ts("12:00", date='2024-02-20'), 10),
        ScheduleEntry(ts("12:00", date='2024-02-20'), ts("00:00", date='2024-02-21'), 20),
    ])


@pytest.fixture
def sample_schedule():
    now = ts('12:34', date='2024-02-20')
    schedule = Schedule(now)
    schedule.add(ts('05:30', date='2024-02-20'), ts('23:30', date='2024-02-20'), 5)
    schedule.add(ts('23:30', date='2024-02-20'), ts('05:30', date='2024-02-21'), 10)
    schedule.add(ts('05:30', date='2024-02-21'), ts('23:30', date='2024-02-21'), 15)
    return schedule


def test_sample_schedule_final(sample_schedule: Schedule):
    compare(sample_schedule.final(), expected=[
        ScheduleEntry(ts("12:30", date='2024-02-20'), ts("23:30", date='2024-02-20'), 5),
        ScheduleEntry(ts("23:30", date='2024-02-20'), ts("05:30", date='2024-02-21'), 10),
        ScheduleEntry(ts("05:30", date='2024-02-21'), ts("12:30", date='2024-02-21'), 15),
    ])


def test_final_times(sample_schedule: Schedule):
    compare(sample_schedule.final_times(), expected=[
        TimeSlot(time(0, 0), time(5, 30), 10),
        TimeSlot(time(5, 30), time(12, 30), 15),
        TimeSlot(time(12, 30), time(23, 30), 5),
        TimeSlot(time(23, 30), time(0, 0), 10),
    ])


def test_final_times_in_eu(sample_schedule: Schedule):
    compare(sample_schedule.final_times(ZoneInfo('Europe/Berlin')), expected=[
        TimeSlot(time(0, 0), time(0, 30), 5),
        TimeSlot(time(0, 30), time(6, 30), 10),
        TimeSlot(time(6, 30), time(13, 30), 15),
        TimeSlot(time(13, 30), time(0, 0), 5),
    ])


def test_final_times_in_us(sample_schedule: Schedule):
    compare(sample_schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(6, 30), cost=15),
        TimeSlot(start=time(6, 30), end=time(17, 30), cost=5),
        TimeSlot(start=time(17, 30), end=time(23, 30), cost=10),
        TimeSlot(start=time(23, 30), end=time(0, 0), cost=15)
    ])


TZ = ZoneInfo('Europe/London')


def add_single_entry_over_dst_misses_hours(schedule: Schedule):
    schedule.add(ts("00:00", '2024-03-31', TZ), ts("03:00", '2024-04-01', TZ), 20)


def expect_single_final_times(schedule, *, cost):
    compare(schedule.final_times(), expected=[
        TimeSlot(start=time(0, 0), end=time(0, 0), cost=cost)
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(0, 0), cost=cost)
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(0, 0), cost=cost)
    ])


def test_single_entry_at_time_before_transition_dst_misses_hours():
    schedule = Schedule(ts("00:00", '2024-03-31', TZ))
    add_single_entry_over_dst_misses_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-31 00:00:00+0000', tz='Europe/London'),
            end=Timestamp('2024-04-01 00:00:00+0100', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def test_single_entry_at_time_after_transition_dst_misses_hours():
    schedule = Schedule(ts("02:00", '2024-03-31', TZ))
    add_single_entry_over_dst_misses_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-31 02:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-04-01 02:00:00+0100', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def add_multiple_entries_over_dst_misses_hours(schedule: Schedule):
    schedule.add(ts("00:00", '2024-03-31', TZ), ts("02:00", '2024-03-31', TZ), 10)
    with ShouldRaise(NonExistentTimeError):
        schedule.add(ts("01:00", '2024-03-31', TZ), ts("02:00", '2024-03-31', TZ), 20)
    schedule.add(ts("02:00", '2024-03-31', TZ), ts("03:00", '2024-03-31', TZ), 30)
    schedule.add(ts("03:00", '2024-03-31', TZ), ts("00:00", '2024-04-01', TZ), 40)
    schedule.add(ts("00:00", '2024-04-01', TZ), ts("03:00", '2024-04-01', TZ), 50)


def test_multiple_entries_at_time_before_transition_dst_misses_hours():
    schedule = Schedule(ts("00:00", '2024-03-31', TZ))
    add_multiple_entries_over_dst_misses_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-31 00:00:00+0000', tz='Europe/London'),
            end=Timestamp('2024-03-31 02:00:00+0100', tz='Europe/London'),
            cost=10
        ),
        ScheduleEntry(
            start=Timestamp('2024-03-31 02:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-03-31 03:00:00+0100', tz='Europe/London'),
            cost=30
        ),
        ScheduleEntry(
            start=Timestamp('2024-03-31 03:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-04-01 00:00:00+0100', tz='Europe/London'),
            cost=40
        ),
    ])
    compare(schedule.final_times(), expected=[
        TimeSlot(start=time(0, 0), end=time(2, 0), cost=10),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=30),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=40),
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(2, 0), cost=10),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=30),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=40),
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(19, 0), cost=40),
        TimeSlot(start=time(19, 0), end=time(20, 0), cost=10),
        TimeSlot(start=time(20, 0), end=time(21, 0), cost=30),
        TimeSlot(start=time(21, 0), end=time(0, 0), cost=40)
    ])


def test_multiple_entries_at_time_after_transition_dst_misses_hours():
    schedule = Schedule(ts("02:00", '2024-03-31', TZ))
    add_multiple_entries_over_dst_misses_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-31 02:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-03-31 03:00:00+0100', tz='Europe/London'),
            cost=30
        ),
        ScheduleEntry(
            start=Timestamp('2024-03-31 03:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-04-01 00:00:00+0100', tz='Europe/London'),
            cost=40
        ),
        ScheduleEntry(
            start=Timestamp('2024-04-01 00:00:00+0100', tz='Europe/London'),
            end=Timestamp('2024-04-01 02:00:00+0100', tz='Europe/London'),
            cost=50
        ),
    ])
    compare(schedule.final_times(), expected=[
        TimeSlot(start=time(0, 0), end=time(2, 0), cost=50),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=30),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=40),
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(2, 0), cost=50),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=30),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=40),
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(18, 0), cost=40),
        TimeSlot(start=time(18, 0), end=time(20, 0), cost=50),
        TimeSlot(start=time(20, 0), end=time(21, 0), cost=30),
        TimeSlot(start=time(21, 0), end=time(0, 0), cost=40),
    ])


def test_compress_edge_case_0000_around_dst_misses_hours():
    tz = ZoneInfo('Europe/London')
    schedule = Schedule(now=ts("00:00", '2024-03-30', tz))
    schedule.add(ts("00:00", '2024-03-30', tz), ts("02:00", '2024-03-31', tz), 10)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-30 00:00:00', tz='Europe/London'),
            end=Timestamp('2024-03-31 00:00:00', tz='Europe/London'),
            cost=10
        ),
    ])
    expect_single_final_times(schedule, cost=10)


def test_compress_edge_case_0100_around_dst_misses_hours():
    tz = ZoneInfo('Europe/London')
    schedule = Schedule(now=ts("01:00", '2024-03-30', tz))
    schedule.add(ts("00:00", '2024-03-30', tz), ts("02:00", '2024-03-31', tz), 11)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-03-30 01:00:00', tz='Europe/London'),
            # weird, 'cos 01:00 doesn't exist, but end up giving correct final_times:
            end=Timestamp('2024-03-31 02:00:00', tz='Europe/London'),
            cost=11
        ),
    ])
    expect_single_final_times(schedule, cost=11)


def add_single_entry_over_dst_extra_hours(schedule: Schedule):
    schedule.add(ts("00:00", '2024-10-27', TZ), ts("03:00", '2024-10-28', TZ), 20)


def test_single_entry_at_time_before_transition_dst_extra_hours():
    schedule = Schedule(ts("00:00", '2024-10-27', TZ))
    add_single_entry_over_dst_extra_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-10-27 00:00:00', tz='Europe/London'),
            end=Timestamp('2024-10-28 00:00:00', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def test_single_entry_at_time_after_transition_dst_extra_hours():
    schedule = Schedule(ts("02:00", '2024-10-27', TZ))
    add_single_entry_over_dst_extra_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp('2024-10-27 02:00:00', tz='Europe/London'),
            end=Timestamp('2024-10-28 02:00:00', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def test_single_entry_during_ambiguous_first_dst_extra_hours():
    schedule = Schedule(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=0)))
    add_single_entry_over_dst_extra_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=1))),
            end=Timestamp('2024-10-28 01:30:00', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def test_single_entry_during_ambiguous_second_dst_extra_hours():
    schedule = Schedule(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=1)))
    add_single_entry_over_dst_extra_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(
            start=Timestamp(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=0))),
            end=Timestamp('2024-10-28 01:30:00', tz='Europe/London'),
            cost=20
        ),
    ])
    expect_single_final_times(schedule, cost=20)


def add_multiple_entries_over_dst_extra_hours(schedule: Schedule):
    schedule.add(ts("00:00", '2024-10-27', TZ), ts("03:00", '2024-10-28', TZ), 20)
    schedule.add(
        ts("00:00", '2024-10-27', TZ),
        Timestamp(datetime(2024, 10, 27, 1, 00, tzinfo=TZ, fold=0)),
        10
    )
    # This one gets lost to the fold:
    schedule.add(
        Timestamp(datetime(2024, 10, 27, 1, 00, tzinfo=TZ, fold=0)),
        Timestamp(datetime(2024, 10, 27, 2, 00, tzinfo=TZ, fold=0)),
        20
    )
    with ShouldAssert("2024-10-27 01:00:00+00:00 <= 2024-10-27 02:00:00+00:00"):
        schedule.add(
            Timestamp(datetime(2024, 10, 27, 2, 00, tzinfo=TZ, fold=0)),
            Timestamp(datetime(2024, 10, 27, 1, 00, tzinfo=TZ, fold=1)),
            30
        )
    schedule.add(
        Timestamp(datetime(2024, 10, 27, 1, 00, tzinfo=TZ, fold=1)),
        Timestamp(datetime(2024, 10, 27, 2, 00, tzinfo=TZ, fold=1)),
        40
    )
    schedule.add(
        Timestamp(datetime(2024, 10, 27, 2, 00, tzinfo=TZ, fold=1)),
        ts("03:00", '2024-10-27', TZ),
        50
    )
    schedule.add(
        ts("03:00", '2024-10-27', TZ),
        ts("00:00", '2024-10-28', TZ),
        60
    )
    schedule.add(
        ts("00:00", '2024-10-28', TZ),
        ts("02:00", '2024-10-28', TZ),
        70
    )
    schedule.add(
        ts("02:00", '2024-10-28', TZ),
        ts("10:00", '2024-10-28', TZ),
        80
    )


def test_multiple_entries_at_time_before_transition_dst_extra_hours():
    schedule = Schedule(ts("00:00", '2024-10-27', TZ))
    add_multiple_entries_over_dst_extra_hours(schedule)
    compare(schedule.final(), expected=[
        ScheduleEntry(start=Timestamp('2024-10-27 00:00:00+0100', tz='Europe/London'),
                      end=Timestamp('2024-10-27 01:00:00+0100', tz='Europe/London'),
                      cost=10),
        ScheduleEntry(start=Timestamp('2024-10-27 01:00:00+0100', tz='Europe/London'),
                      end=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      cost=40),
        ScheduleEntry(start=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      cost=50),
        ScheduleEntry(start=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-28 00:00:00+0000', tz='Europe/London'),
                      cost=60),
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(1, 0), cost=10),
        TimeSlot(start=time(1, 0), end=time(2, 0), cost=40),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=50),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=60),
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(18, 0), cost=60),
        TimeSlot(start=time(18, 0), end=time(19, 0), cost=10),
        TimeSlot(start=time(19, 0), end=time(21, 0), cost=40),
        TimeSlot(start=time(21, 0), end=time(22, 0), cost=50),
        TimeSlot(start=time(22, 0), end=time(0, 0), cost=60),
    ])


def test_multiple_entries_at_time_after_transition_dst_extra_hours():
    schedule = Schedule(ts("02:00", '2024-10-27', TZ))
    add_multiple_entries_over_dst_extra_hours(schedule)
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(2, 0), cost=70),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=50),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=60)
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(19, 0), cost=60),
        TimeSlot(start=time(19, 0), end=time(21, 0), cost=70),
        TimeSlot(start=time(21, 0), end=time(22, 0), cost=50),
        TimeSlot(start=time(22, 0), end=time(0, 0), cost=60)
    ])


def test_multiple_entries_during_ambiguous_first_dst_extra_hours():
    schedule = Schedule(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=0)))
    add_multiple_entries_over_dst_extra_hours(schedule)
    # We have fold=1 here, but that'll basically be ignored by everything:
    compare(schedule.final(), expected=[
        ScheduleEntry(start=Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=1)),
                      end=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      cost=40),
        ScheduleEntry(start=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      cost=50),
        ScheduleEntry(start=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-28 00:00:00+0000', tz='Europe/London'),
                      cost=60),
        ScheduleEntry(start=Timestamp('2024-10-28 00:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-28 01:30:00+0000', tz='Europe/London'),
                      cost=70),
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        # This fold=1 will be ignored too:
        TimeSlot(start=time(0, 0), end=time(1, 30, fold=1), cost=70),
        TimeSlot(start=time(1, 30, fold=1), end=time(2, 0), cost=40),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=50),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=60),
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(19, 0), cost=60),
        TimeSlot(start=time(19, 0), end=time(20, 30), cost=70),
        TimeSlot(start=time(20, 30), end=time(21, 0), cost=40),
        TimeSlot(start=time(21, 0), end=time(22, 0), cost=50),
        TimeSlot(start=time(22, 0), end=time(0, 0), cost=60)
    ])


def test_multiple_entries_during_ambiguous_second_dst_extra_hours():
    schedule = Schedule(Timestamp(datetime(2024, 10, 27, 1, 30, tzinfo=TZ, fold=1)))
    add_multiple_entries_over_dst_extra_hours(schedule)
    # We have fold=1 here, but that'll basically be ignored by everything:
    compare(schedule.final(), expected=[
        ScheduleEntry(start=Timestamp('2024-10-27 01:30:00+0100', tz='Europe/London'),
                      end=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      cost=40),
        ScheduleEntry(start=Timestamp('2024-10-27 02:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      cost=50),
        ScheduleEntry(start=Timestamp('2024-10-27 03:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-28 00:00:00+0000', tz='Europe/London'),
                      cost=60),
        ScheduleEntry(start=Timestamp('2024-10-28 00:00:00+0000', tz='Europe/London'),
                      end=Timestamp('2024-10-28 01:30:00+0000', tz='Europe/London'),
                      cost=70),
    ])
    compare(schedule.final_times(ZoneInfo('Europe/London')), expected=[
        TimeSlot(start=time(0, 0), end=time(1, 30), cost=70),
        TimeSlot(start=time(1, 30), end=time(2, 0), cost=40),
        TimeSlot(start=time(2, 0), end=time(3, 0), cost=50),
        TimeSlot(start=time(3, 0), end=time(0, 0), cost=60),
    ])
    compare(schedule.final_times(ZoneInfo('America/Chicago')), expected=[
        TimeSlot(start=time(0, 0), end=time(19, 0), cost=60),
        TimeSlot(start=time(19, 0), end=time(19, 30), cost=70),
        TimeSlot(start=time(19, 30), end=time(21, 0), cost=40),
        TimeSlot(start=time(21, 0), end=time(22, 0), cost=50),
        TimeSlot(start=time(22, 0), end=time(0, 0), cost=60)
    ])
