# -*- coding: utf-8 -*-

import first
import logging
import path
import socket
import sys
import xmlrpclib


from . import core
from . import daemon


class WatsonClient(xmlrpclib.ServerProxy):

    def __init__(self):
        self.endpoint = ('localhost', 0x221B)
        xmlrpclib.ServerProxy.__init__(self, 'http://%s:%s/' % self.endpoint,
                                       allow_none=True)

    def watch(self, working_dir="."):
        project_dir = core.find_project_directory(working_dir)

        config_files = [project_dir / n for n in core.CONFIG_FILENAMES]
        config_file = first.first(config_files, key=lambda x: x.exists())

        if config_file is None:
            raise core.WatsonError(
                'project under %s has no config' % project_dir)

        config = core.load_config(config_file)

        # TODO(dejw): write a test for marshaling path.path objects
        self.add_project(unicode(project_dir), config)


def main():
    """usage: watson watch

    Repository watcher - watches for filesystem changes of your project and
    constantly builds it and keeps you posted about the build status.

    Commands:

      watch     starts watching a project or updates its status if it was
                already being watched

    """
    if len(sys.argv) < 2:
        print main.__doc__.strip()
        return

    command = sys.argv[1]

    if command in ['start', 'stop', 'restart']:
        daemon.WatsonDaemon().perform(command, fork=True)

    if command == 'watch':
        logging.basicConfig(level=logging.INFO,
                            format='%(levelname)7s: %(message)s')

        client = WatsonClient()

        try:
            version = client.hello()
        except socket.error:
            logging.warning('Could not connect to Watson server; Spawning one')
            daemon.WatsonDaemon().perform('start', fork=True)
            try:
                version = client.hello()
            except socket.error:
                raise core.WatsonError('Could not connect to the local watson '
                                       'server at %s' % (client.endpoint,))
        logging.info('Connected to %s' % version)

        client.watch()

if __name__ == '__main__':
    main()
