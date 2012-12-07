# -*- coding: utf-8 -*-

import collections
import its
import mox
import path
import SimpleXMLRPCServer
import tempfile

try:
    import unittest2 as unittest
except ImportError:
    if not its.py27:
        raise
    import unittest

from fabric import context_managers
from fabric import operations
from watchdog import observers

from . import core


class TestBase(unittest.TestCase):

    def setUp(self):
        self.mox = mox.Mox()

    def tearDown(self):
        self.mox.UnsetStubs()


class TestFindProjectDirectory(unittest.TestCase):

    def test_simple(self):
        look_for = ['requirements.txt']
        start = path.path(__file__).dirname()

        directory = core.find_project_directory(start, look_for=look_for)

        self.assertEqual(start.parent, directory)

    def test_WatsonError_dir_is_not_part_of_project(self):
        with self.assertRaises(core.WatsonError):
            _ = core.find_project_directory(tempfile.gettempdir())


class HeadlessProjectWatcher(core.ProjectWatcher):

    def _create_notification(self):
        pass

    def _show_notification(self, status):
        self._last_status = status


class TestProjectWatcher(TestBase):

    @classmethod
    def setUpClass(self):
        self._project_dir = core.find_project_directory(
            path.path(__file__).dirname())

    def setUp(self):
        super(TestProjectWatcher, self).setUp()

        self.directory = 'a directory'
        self.watch = 'a watch'

        self.observer_mock = self.mox.CreateMock(observers.Observer)
        self.worker_mock = self.mox.CreateMock(core.ProjectBuilder)

        (self.observer_mock.schedule(
            mox.IsA(core.ProjectWatcher), path=self.directory, recursive=True)
            .AndReturn(self.watch))

    def get_watcher(self):
        return HeadlessProjectWatcher('test', self.directory, self.worker_mock,
                                      self.observer_mock)

    def test_init(self):
        self.mox.ReplayAll()

        self.get_watcher()

        self.mox.VerifyAll()

    def test_shutdown(self):
        self.observer_mock.unschedule(self.watch)
        self.mox.ReplayAll()

        self.get_watcher().shutdown(self.observer_mock)

        self.mox.VerifyAll()

    def test_on_any_event(self):
        status = (True, None)
        (self.worker_mock.execute_script(self.directory, ['nosetests'])
            .AndReturn(status))
        self.mox.ReplayAll()

        watcher = self.get_watcher()
        watcher.on_any_event(None)

        self.mox.VerifyAll()
        self.assertEqual(status, watcher._last_status)


class HeadlessWatsonServer(core.WatsonServer):

    def _init_pynotify(self):
        pass


class TestWatsonServer(TestBase):

    def setUp(self):
        super(TestWatsonServer, self).setUp()

        self.mox.StubOutClassWithMocks(SimpleXMLRPCServer,
                                       "SimpleXMLRPCServer")

        hostport = ("localhost", 0x221B)
        self.server_mock = SimpleXMLRPCServer.SimpleXMLRPCServer(hostport)
        self.server_mock.register_instance(mox.IsA(core.WatsonServer))
        self.server_mock.serve_forever()

    def test_init(self):
        self.mox.ReplayAll()

        HeadlessWatsonServer()

        self.mox.VerifyAll()

    def test_shutdown(self):
        self.server_mock.server_close()

        self.mox.StubOutClassWithMocks(core, "ProjectBuilder")
        worker_mock = core.ProjectBuilder(processes=1)
        worker_mock.close()
        worker_mock.join()

        self.mox.StubOutClassWithMocks(observers, "Observer")
        observer_mock = observers.Observer()
        observer_mock.stop()
        observer_mock.join()

        self.mox.ReplayAll()

        HeadlessWatsonServer().shutdown()

        self.mox.VerifyAll()


class ResultMock(collections.namedtuple('ResultMock', ['succeeed', 'msg'])):
    pass


class TestProjectBuilder(TestBase):

    def setUp(self):
        super(TestProjectBuilder, self).setUp()

        self.working_dir = 'a directory'

        lcd_mock = self.mox.CreateMockAnything()
        lcd_mock.__enter__()
        lcd_mock.__exit__(mox.IgnoreArg(), mox.IgnoreArg(), mox.IgnoreArg())
        self.mox.StubOutWithMock(context_managers, 'lcd')
        context_managers.lcd(self.working_dir).AndReturn(lcd_mock)

    def _stubout_local(self, script, results):
        self.mox.StubOutWithMock(operations, 'local')
        for command, result in zip(script, results):
            operations.local(command, capture=True).AndReturn(
                ResultMock(result, command))

    def test_execute_script_internal(self):
        script = ['echo 1', 'echo 2']
        self._stubout_local(script, [True, True])

        self.mox.ReplayAll()

        worker = core.ProjectBuilder()
        result = worker._execute_script_internal(self.working_dir, script)

        self.mox.VerifyAll()
        self.assertEqual((True, ResultMock(True, script[-1])), result)

    def test_execute_runs_until_first_failure(self):
        script = ['echo 1', 'echo 2', 'echo 3']

        # only first two commands are passed to operations.local
        self._stubout_local(script[:2], [True, False])
        self.mox.ReplayAll()

        worker = core.ProjectBuilder()
        result = worker._execute_script_internal(self.working_dir, script)

        self.mox.VerifyAll()
        self.assertEqual((False, ResultMock(False, script[1])), result)


if __name__ == '__main__':
    unittest.main()
