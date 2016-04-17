#!/usr/bin/env python

from arrow import arrow
import time
import user

import sqlalchemy
from sqlalchemy import orm
from sqlalchemy.ext import declarative

Base = declarative.declarative_base()

def totimestamp(dt):
    return time.mktime(dt.timetuple()) + getattr(dt, "microsecond", 0)/1e6

class entry(Base):
    __tablename__ = "entry"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    sheet = sqlalchemy.Column(sqlalchemy.VARCHAR(32)) # not null
    start_time = sqlalchemy.Column(sqlalchemy.Integer) # not null
    end_time = sqlalchemy.Column(sqlalchemy.Integer)
    description = sqlalchemy.Column(sqlalchemy.VARCHAR(64))
    extra = sqlalchemy.Column(sqlalchemy.BLOB)

    @property
    def start(self):
        return arrow.datetime.fromtimestamp(self.start_time)

    @start.setter
    def set_start(self, new_start):
        self.start_time = totimestamp(new_start)

    @property
    def end(self):
        return arrow.datetime.fromtimestamp(self.end_time)

    @end.setter
    def set_end(self, new_end):
        self.end_time = totimestamp(new_end)

    @property
    def duration(self):
        return arrow.timedelta(seconds=(self.end_time-self.start_time))

class toggl_id_map(Base):
    __tablename__ = "toggl_id_map"
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
    entry_id = sqlalchemy.Column(sqlalchemy.Integer)
    toggl_id = sqlalchemy.Column(sqlalchemy.Integer)
    toggl_at = sqlalchemy.Column(sqlalchemy.Integer)

    @property
    def toggl_at_date(self):
        return arrow.datetime.fromtimestamp(self.toggl_at)

    @toggl_at_date.setter
    def toggl_at_date(self, new_at):
        self.toggl_at = totimestamp(new_toggl_at)

