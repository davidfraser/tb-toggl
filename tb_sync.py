#!/usr/bin/env python

from tb_db import *
import argparse
import os
import locale
import arrow
import tapioca_toggl
import ConfigParser
import logging

tb_confdir = os.path.expanduser(os.path.join('~', '.config', 'timebook'))
DEFAULTS = {'config': os.path.join(tb_confdir, 'timebook.ini'),
            'timebook': os.path.join(tb_confdir, 'sheets.db'),
            'encoding': locale.getpreferredencoding()}

toggl_conf_file = os.path.expanduser(os.path.join('~', '.togglrc'))
toggl_conf = ConfigParser.RawConfigParser()
toggl_conf.read(toggl_conf_file)

toggl_api = tapioca_toggl.Toggl(access_token=toggl_conf.get('auth', 'api_token'))
me = toggl_api.me_with_related_data().get()
toggl_tz = me.data.timezone().data

pid_by_name = {project.name().data: project.id().data for project in me.data.projects}

def get_project(sheet_name, tags):
    for tag in sorted(tags):
        possible_project = '%s-%s' % (sheet_name, tag)
        if possible_project in pid_by_name:
            return pid_by_name[possible_project]
    if sheet_name + '-misc' in pid_by_name:
        return pid_by_name['%s-misc' % sheet_name]
    if sheet_name in pid_by_name:
        return pid_by_name[sheet_name]

def send_to_toggl(session, date_start, date_end):
    q = session.query(entry)
    if date_start:
        q = q.filter(entry.end_time >= totimestamp(date_start))
    if date_end:
        q = q.filter(entry.start_time <= totimestamp(date_end))
    synced_entries = session.query(toggl_id_map.entry_id)
    q = q.filter(~entry.id.in_(synced_entries))
    time_entries = toggl_api.time_entries()
    for e in q:
        fd = lambda d: arrow.get(d).to('utc').isoformat()
        tags = [w for w in e.description.split() if w and w[0] in '+@']
        pid = get_project(e.sheet, [tag[1:] for tag in tags if tag.startswith('+')])
        if pid is None:
            logging.warning("Could not work out project name for %s", e.description)
            continue
        data_to_toggl = {'description': e.description, 'pid': pid, 'created_with': 'tb-toggl',
                         'start': fd(e.start), 'stop': fd(e.end), 'duration': e.duration.seconds,
                         'tags': tags}
        print(data_to_toggl)
        try:
            toggl_dict = time_entries.post(data={'time_entry': data_to_toggl}).data()._data
        except Exception, error:
            logging.error("Error synchronizing: %s with data %r", error, data_to_toggl)
            continue
        toggl_id, toggl_at = toggl_dict['id'], toggl_dict['at']
        new_map = toggl_id_map(entry_id=e.id, toggl_id=toggl_id, toggl_at=toggl_at)
        session.add(new_map)
        session.commit()

def resync_to_toggl(session, date_start, date_end):
    q = session.query(entry, toggl_id_map)
    if date_start:
        q = q.filter(entry.end_time >= totimestamp(date_start))
    if date_end:
        q = q.filter(entry.start_time <= totimestamp(date_end))
    synced_entries = session.query(toggl_id_map.entry_id)
    q = q.filter(entry.id.in_(synced_entries))
    time_entries = toggl_api.time_entries()
    for result in q:
        e = result.entry
        e_map = result.toggl_id_map
        fd = lambda d: arrow.get(d).to('utc').isoformat()
        tags = [w for w in e.description.split() if w and w[0] in '+@']
        pid = get_project(e.sheet, [tag[1:] for tag in tags if tag.startswith('+')])
        if pid is None:
            logging.warning("Could not work out project name for %s", e.description)
            continue
        data_to_toggl = {'description': e.description, 'pid': pid, 'created_with': 'tb-toggl',
                         'start': fd(e.start), 'stop': fd(e.end), 'duration': e.duration.seconds,
                         'tags': tags, 'id': e_map.toggl_id}
        print(data_to_toggl)
        print(e_map)
        try:
            toggl_dict = toggl_api.time_entries(id=e_map.toggl_id).put(data={'time_entry': data_to_toggl}).data()._data
        except Exception, error:
            logging.error("Error synchronizing: %s with data %r", error, data_to_toggl)
            continue
        toggl_id, toggl_at = toggl_dict['id'], toggl_dict['at']
        if toggl_id != e_map.toggl_id:
            logging.warning("map mismatch: %r %r", toggl_dict, e_map)
        else:
            e_map.toggl_at = toggl_at
        session.commit()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timebook", action="store_true", default=DEFAULTS["timebook"])
    options = parser.parse_args()
    db_file = options.timebook
    engine = sqlalchemy.create_engine("sqlite:///%s" % db_file)
    Base.metadata.create_all(engine)
    session_class = orm.sessionmaker(bind=engine)
    session = session_class()
    resync_to_toggl(session, arrow.utcnow().replace(days=-7), arrow.utcnow())

if __name__ == '__main__':
    main()

