# -*- coding: utf-8 -*-

import os
import path
import xmlrpclib

from fabric import context_managers
from fabric import operations
from multiprocessing import pool
from watchdog import events
from watchdog import observers


DEFAULT_PROJECT_INDICATORS = ['.watson.yaml', '.vip', 'setup.py']


class WatsonError(StandardError):
    pass


def find_project_directory(start=".", look_for=None):
    """Finds a directory that looks like a project directory.

    The search is performed up in the directory tree, and is finished when
    one of the terminators is found.

    Args:
        start: a path (directory) from where the search is started
            "." by default
        look_for: a list of search terminators,
            core.DEFAULT_PROJECT_INDICATORS by default

    Returns:
        A path to a directory that contains one of terminators

    Raises:
        WatsonError: when no such directory can be found
    """
    look_for = set(look_for or DEFAULT_PROJECT_INDICATORS)

    directory = path.path(start).abspath()

    while directory.parent != directory:
        items = os.listdir(directory)
        if any(i in look_for for i in items):
            return directory

        directory = directory.parent

    raise WatsonError('%s does not look like a project subdirectory' % start)


class ProjectWatcher(events.FileSystemEventHandler):

    # TODO(dejw): should expose some stats (like how many times it was
    #             notified) or how many times it succeeed in testing etc.

    def __init__(self, name, directory, worker, observer):
        self._name = name
        self._directory = directory
        self._last_status = (None, None)
        self._notification = pynotify.Notification('')
        self._notification.set_timeout(5)

        self._worker = worker
        # TODO(dejw): allow to change observing patterns (and recursiveness)
        self._watch = observer.schedule(self, path=self._directory,
                                        recursive=True)

    def shutdown(self, observer):
        observer.unschedule(self._watch)

    def on_any_event(self, event):
        status = self._worker.execute_script(self._directory, ['nosetests'])
        self._show_notification(result)

    def _show_notification(self, status):
        succeeed, result = status

        if succeeed != self._last_status[0]:
            if not succeeed:
                self._notification.update('%s failed' % self._name,
                                          result.stderr.splitlines()[-1])
            else:
                self._notification.update('%s back to normal' % self._name,
                                          'Suberb!')

            self._notification.show()

        self._last_status = status


class ProjectBuilder(pool.ThreadPool):

    def execute_script(self, working_dir, script):
        return self.apply(self._execute_script_internal, working_dir, script)

    def _execute_script_internal(self, working_dir, script):
        succeeed = True
        result = None

        with context_managers.lcd(working_dir):
            for command in script:
                result = operations.local(command, capture=True)
                succeeed = succeeed and result.succeeed
                if not succeeed:
                    break

        return (succeeed, result)


class WatsonServer(object):

    def __init__(self):
        # TODO(dejw): allow to change number of workers
        self._pool = ProjectBuilder(processes=1)
        self._projects = {}
        self._observer = observers.Observer()

        self._init_pynotify()

        # TODO(dejw): read (host, port) from config in user's directory
        self._api = SimpleXMLRPCServer.SimpleXMLRPCServer(
            ('localhost', 0x221B))
        self._api.register_instance(self)
        self._api.serve_forever()

    @classmethod
    def get_server_proxy(cls):
        return xmlrpclib.ServerProxy("http://%s:%s/" % ('localhost', 0x221B))

    def _init_pynotify(self):
        pynotify.init("Watson")
        assert pynotify.get_server_caps() is not None

    def shutdown(self):
        self._api.shutdown()

        self._pool.close()
        self._pool.join()

        self._observer.stop()
        self._observer.join()

    # TODO(dejw): handle config file case
    def add_project(self, directory):
        directory = path.path(directory)
        assert directory.isdir()

        # TODO(dejw): load a name from config if available
        name = directory.name
        self._project[name] = ProjectWatcher(name, directory, self._pool,
                                             self._observer)
