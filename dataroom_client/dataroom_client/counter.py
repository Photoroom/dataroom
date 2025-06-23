import datetime
import zoneinfo

from .print_utils import print_success


class Counter:
    def __init__(self, total, use_print=True, print_every=10):
        self.total = total
        self.count = 0
        self.use_print = use_print
        self.print_every = print_every
        self.start_time = None
        self.end_time = None

    @property
    def time_left(self):
        elapsed = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC')) - self.start_time
        seconds_left = (self.total - self.count) * elapsed.total_seconds() / self.count
        return datetime.timedelta(seconds=seconds_left)

    @property
    def time_took(self):
        return self.end_time - self.start_time

    @property
    def percent(self):
        return round(self.count / self.total * 100, 1)

    def increment(self):
        self.count += 1
        if self.use_print and self.print_every and self.count % self.print_every == 0:
            print_success(
                f'Processed {self.percent}% - {self.count} out of {self.total}. Time left: {self.time_left}',
            )

    def start(self):
        self.start_time = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC'))

    def end(self):
        self.end_time = datetime.datetime.now(tz=zoneinfo.ZoneInfo('UTC'))
        if self.use_print:
            print_success(
                f'Done! Took: {self.time_took}',
            )
