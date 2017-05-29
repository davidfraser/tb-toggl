#!/usr/bin/env python

from tb_db import *
import argparse
import os
import locale
from datetime import datetime, timedelta
import toggl
import logging
import json
import pytz

tb_confdir = os.path.expanduser(os.path.join('~', '.config', 'timebook'))
DEFAULTS = {'config': os.path.join(tb_confdir, 'timebook.ini'),
            'timebook': os.path.join(tb_confdir, 'sheets.db'),
            'encoding': locale.getpreferredencoding()}

UTC = pytz.timezone("UTC")
localtz = toggl.DateAndTime().tz

def get_project(sheet_name, tags):
    project_list = toggl.ProjectList()
    projects = {project['name']: project for project in project_list}
    for possible_project in ['%s-%s' % (sheet_name, tag) for tag in tags] + ['%s-misc' % sheet_name, sheet_name]:
        if possible_project in projects:
            return projects[possible_project]

def fd(d):
    """formats a date in the local timezone in isoformat"""
    d = localtz.localize(d)
    return d.isoformat()

def send_to_toggl(session, date_start, date_end):
    q = session.query(entry)
    if date_start:
        q = q.filter(entry.end_time >= totimestamp(date_start))
    if date_end:
        q = q.filter(entry.start_time <= totimestamp(date_end))
    synced_entries = session.query(toggl_id_map.entry_id)
    q = q.filter(~entry.id.in_(synced_entries))
    q = q.order_by(sqlalchemy.desc(entry.start_time))
    for e in q:
        if e.description is None:
            logging.warning("Entry id %s from %s to %s has no description: not adding", e.id, e.start, e.end)
            continue
        tags = [w for w in e.description.split() if w and w[0] in '+@']
        project = get_project(e.sheet, [tag[1:] for tag in tags if tag.startswith('+')])
        if project is None:
            logging.warning("Could not work out project name for id %s (%s to %s) - description %s: not adding", e.id, e.start, e.end, e.description)
            continue
        toggl_data = {'description': e.description, 'pid': project['id'], 'start': fd(e.start), 'stop': fd(e.end), 'duration': e.duration.seconds, 'tags': tags}
        toggl_entry = toggl.TimeEntry(data_dict=toggl_data)
        toggl_entry.data['create_with'] = 'tb-toggl'
        try:
            r = toggl_entry.add()
        except Exception, error:
            logging.error("Error synchronizing: %s with data %r", error, toggl_data)
            continue
        if r is None:
            logging.error("Error adding (None returned): %r", toggl_data)
            continue
        toggl_dict = json.loads(r)["data"]
        toggl_id, toggl_at = toggl_dict['id'], toggl_dict['at']
        new_map = toggl_id_map(entry_id=e.id, toggl_id=toggl_id, toggl_at=toggl_at)
        session.add(new_map)
        session.commit()
        logging.info("Mapped entry %s (%s to %s) to toggl id %s: %s", e.id, e.start, e.end, toggl_id, e.description)

def resync_to_toggl(session, date_start, date_end):
    q = session.query(entry, toggl_id_map)
    if date_start:
        q = q.filter(entry.end_time >= totimestamp(date_start))
    if date_end:
        q = q.filter(entry.start_time <= totimestamp(date_end))
    q = q.filter(entry.id == toggl_id_map.entry_id)
    q = q.order_by(sqlalchemy.desc(entry.start_time))
    for result in q:
        e = result.entry
        e_map = result.toggl_id_map
        tags = [w for w in e.description.split() if w and w[0] in '+@']
        project = get_project(e.sheet, [tag[1:] for tag in tags if tag.startswith('+')])
        if project is None:
            logging.warning("Could not work out project name for %s: not updating", e.description)
            continue
        toggl_data = {'description': e.description, 'pid': project['id'], 'created_with': 'tb-toggl',
                      'start': fd(e.start), 'stop': fd(e.end), 'duration': e.duration.seconds,
                      'tags': tags, 'id': e_map.toggl_id}
        toggl_entry = toggl.TimeEntry(data_dict=toggl_data)
        toggl_entry.data['create_with'] = 'tb-toggl'
        try:
            r = toggl.toggl("%s/time_entries/%s" % (toggl.TOGGL_URL, toggl_entry.data['id']), 'put', data=toggl_entry.json())
        except Exception, error:
            logging.error("Error synchronizing: %s with data %r", error, toggl_data)
            continue
        toggl_dict = json.loads(r)["data"]
        toggl_id, toggl_at = toggl_dict['id'], toggl_dict['at']
        if toggl_id != e_map.toggl_id:
            logging.warning("map mismatch: %r %r", toggl_dict, e_map)
        else:
            e_map.toggl_at = toggl_at
            logging.info("Updated toggl id %s from entry %s (%s to %s) at %s: %s", toggl_id, e.id, e.start, e.end, toggl_at, e.description)
        session.commit()

def main():
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger("requests").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser()
    parser.add_argument("--timebook", action="store_true", default=DEFAULTS["timebook"])
    options = parser.parse_args()
    db_file = options.timebook
    engine = sqlalchemy.create_engine("sqlite:///%s" % db_file)
    Base.metadata.create_all(engine)
    session_class = orm.sessionmaker(bind=engine)
    session = session_class()
    # resync_to_toggl(session, localtz.localize(datetime.now() - timedelta(days=2)), localtz.localize(datetime.now()))
    send_to_toggl(session, localtz.localize(datetime.now() - timedelta(days=7200)), localtz.localize(datetime.now()))

if __name__ == '__main__':
    main()

