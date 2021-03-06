import time
import unittest
from unittest import mock

import libtmux

from symphony.engine import *
from symphony import errors
from symphony import tmux


_TEST_SERVER = '__symphony_test__'

_TEST_DUMP = {
    'process_groups': [
        {
            'processes': [
                {
                    'name': 'hello',
                    'binded_services': {},
                    'connected_services': {},
                    'exposed_services': {},
                    'start_dir': '.',
                    'cmds': ['echo Hello World!'],
                }
            ],
            'name': 'group',
            'start_dir': '.',
            'preamble_cmds': [],
        }
    ],
    'processes': [
        {
            'name': 'alone',
            'binded_services': {},
            'connected_services': {},
            'exposed_services': {},
            'start_dir': '.',
            'cmds': ['echo I am alone'],
        }
    ],
    'name': 'exp',
    'ab': {},
    'port_range': '7000-8999',
    'start_dir': '.',
    'preamble_cmds': [],
}


class TestTmuxCluster(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Create a temporary Tmux server for testing.
        libtmux.Server(socket_name=_TEST_SERVER).kill_server()
        cls.mock_server_name = mock.patch.object(
                tmux.cluster, '_SERVER_NAME', new=_TEST_SERVER)
        cls.mock_server_name.start()

    @classmethod
    def tearDownClass(cls):
        libtmux.Server(socket_name=_TEST_SERVER).kill_server()
        cls.mock_server_name.stop()

    def setUp(self):
        self.server = libtmux.Server(socket_name=_TEST_SERVER)

    def tearDown(self):
        # Catch-all try block for clean teardown after each test.
        try:
            for sess in self.server.sessions:
                sess.kill_session()
        except:
            pass

    def create_default_experiment(self, exp_preamble=[], group_preamble=[],
                                  launch=True):
        # Create and launch default experiment used by most test cases.
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        # Create specs.
        exp = cluster.new_experiment('exp', preamble_cmds=exp_preamble)
        group = exp.new_process_group('group', preamble_cmds=group_preamble)
        echo_proc = group.new_process('hello', cmds=['echo Hello World!'])
        lone_proc = exp.new_process('alone', cmds=['echo I am alone'])

        if launch:
          cluster.launch(exp)

        return exp

    #################### Spec tests ####################

    def test_config_validation(self):
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        with self.assertRaises(ValueError):
            cluster.new_experiment(None)
            cluster.new_experiment('')
            cluster.new_experiment('invalid:name')
            cluster.new_experiment('invalid.name')

        exp = cluster.new_experiment('valid_name')
        with self.assertRaises(ValueError):
            exp.new_process_group(None)
            exp.new_process_group('')
            exp.new_process_group('invalid:name')
            exp.new_process_group('invalid.name')
            exp.new_process(None, '')
            exp.new_process('', '')
            exp.new_process('invalid:name', '')
            exp.new_process('invalid.name', '')

        group = exp.new_process_group('group')
        with self.assertRaises(ValueError):
            group.new_process('', '')
            group.new_process('invalid:name', '')
            group.new_process('invalid.name', '')

        group.new_process('Joy', ['echo Success!'])

    #################### Launch API tests ####################

    def test_empty_experiment(self):
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        exp = cluster.new_experiment('empty_exp')
        cluster.launch(exp)
        # Confirm the launch of experiment on tmux side.
        self.assertListEqual([s.name for s in self.server.sessions],
                             ['empty_exp'])

        # Check windows
        sess = self.server.sessions[0]
        self.assertCountEqual([tmux.cluster._DEFAULT_WINDOW],
                              [w.name for w in sess.windows])

    def test_launch_experiment(self):
        self.create_default_experiment()
        # Confirm the launch of experiment on tmux side.
        self.assertListEqual([s.name for s in self.server.sessions], ['exp'])

        # One window for each of: default, group:hello, alone
        sess = self.server.sessions[0]
        self.assertCountEqual(
                [tmux.cluster._DEFAULT_WINDOW, 'group:hello', 'alone'],
                [w.name for w in sess.windows])

    def test_multiple_experiments(self):
        self.create_default_experiment()

        # Launch a second experiment.
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        exp2 = cluster.new_experiment('exp2')
        cluster.launch(exp2)

        # Confirm the launch of experiment on tmux side.
        self.assertListEqual([s.name for s in self.server.sessions],
                             ['exp', 'exp2'])

        # Check windows
        sess = self.server.sessions[0]
        self.assertCountEqual(
                [tmux.cluster._DEFAULT_WINDOW, 'group:hello', 'alone'],
                [w.name for w in sess.windows])
        sess = self.server.sessions[1]
        self.assertCountEqual([tmux.cluster._DEFAULT_WINDOW],
                              [w.name for w in sess.windows])

    def test_duplicate_names(self):
        self.create_default_experiment()

        # Attempt creating a session with duplicate name
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        dupe = cluster.new_experiment('exp')

        with self.assertRaises(errors.ResourceExistsError):
            cluster.launch(dupe)

        # Attempt creating a process with duplicate name
        dupe = cluster.new_experiment('exp')
        dupe.new_process('alone', ['echo Do I exist already?'])

        with self.assertRaises(errors.ResourceExistsError):
            cluster.launch(dupe)

    #################### Query API tests ####################

    def test_list_experiment(self):
        self.create_default_experiment()
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        experiments = cluster.list_experiments()
        self.assertListEqual(experiments, ['exp'])

    def test_describe_experiment(self):
        self.create_default_experiment()
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        with self.assertRaises(ValueError):
            cluster.describe_experiment('Irene')
        exp_dict = cluster.describe_experiment('exp')
        self.assertDictEqual(
                exp_dict,
                {
                    'group': {
                        'hello': {
                            'status': 'live'
                        }
                    },
                    None: {
                        'alone': {
                            'status': 'live'
                        },
                    },
                }
        )

    def test_describe_process_group(self):
        self.create_default_experiment()
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        with self.assertRaises(ValueError):
            cluster.describe_process_group('bad_exp', 'group')
            cluster.describe_process_group('exp', 'bad_group')
        group_dict = cluster.describe_process_group('exp', 'group')
        self.assertDictEqual(group_dict,
                {
                    'hello': {
                        'status': 'live'
                    }
                }
        )
        group_dict = cluster.describe_process_group('exp', None)
        self.assertDictEqual(group_dict,
                    {
                        'alone': {
                            'status': 'live'
                        },
                    }
        )

    def test_describe_process(self):
        self.create_default_experiment()
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        with self.assertRaises(ValueError):
            cluster.describe_process('bad_exp', 'hello')
            cluster.describe_process('exp', 'bad_process')
            cluster.describe_process('exp', None)
            cluster.describe_process('exp', None, process_group_name='group')
            cluster.describe_process('exp', '')
            cluster.describe_process('exp', '', process_group_name='group')
            cluster.describe_process('exp', 'hello')
            cluster.describe_process('exp', 'bad_process',
                                      process_group_name='group')
            cluster.describe_process('exp', 'alone',
                                      process_group_name='group')
        process_dict = cluster.describe_process('exp', 'hello',
                                                process_group_name='group')
        self.assertDictEqual(process_dict, { 'status': 'live' })
        process_dict = cluster.describe_process('exp', 'alone')
        self.assertDictEqual(process_dict, { 'status': 'live' })

    def test_get_log(self):
        self.create_default_experiment()
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        l = cluster.get_log('exp', 'hello', process_group='group')
        self.assertIn('Hello World!', l)

    def test_experiment_preamble(self):
        self.create_default_experiment(exp_preamble=['echo exp preamble'])
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        l = cluster.get_log('exp', 'hello', process_group='group')
        self.assertIn('exp preamble', l)

        l = cluster.get_log('exp', 'alone')
        self.assertIn('exp preamble', l)

    def test_process_group_preamble(self):
        self.create_default_experiment(exp_preamble=['echo exp preamble'],
                                       group_preamble=['echo group preamble'])
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)

        l = cluster.get_log('exp', 'hello', process_group='group')
        self.assertIn('exp preamble', l)
        self.assertIn('group preamble', l)
        self.assertLess(l.index('exp preamble'), l.index('group preamble'))

        l = cluster.get_log('exp', 'alone')
        self.assertIn('exp preamble', l)
        self.assertNotIn('group preamble', l)

    #################### Action API tests ####################

    def test_delete(self):
        self.create_default_experiment()

        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        with self.assertRaises(ValueError):
            # cluster.delete(None)
            # cluster.delete('')
            cluster.delete('Irene')
        self.assertListEqual(cluster.list_experiments(), ['exp'])
        cluster.delete('exp')
        self.assertListEqual(cluster.list_experiments(), [])


    def test_transfer_file(self):
        # TODO
        pass

    def test_login(self):
        # TODO
        pass

    def test_exec_command(self):
        # TODO
        pass

    #################### Process exec tests ####################
    def test_process_exec(self):
        self.create_default_experiment()

    #################### Port tests ####################

    def test_ports(self):
        # XXX
        pass

    #################### Serialization tests ####################

    def test_dump_dict(self):
        exp = self.create_default_experiment(launch=False)
        dump = exp.dump_dict()
        self.assertDictEqual(dump, _TEST_DUMP);

    def test_load_dict(self):
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        exp = tmux.TmuxExperimentSpec.load_dict(_TEST_DUMP)
        group = list(exp.list_process_groups())
        procs = list(exp.list_all_processes())
        self.assertEqual(len(group), 1)
        self.assertEqual(len(procs), 2)
        self.assertEqual(group[0].name, 'group')
        self.assertSetEqual({x.name for x in procs}, {'hello', 'alone'})

    def test_serialization_idempotence(self):
        cluster = Cluster.new('tmux', server_name=_TEST_SERVER)
        exp = self.create_default_experiment(launch=False)
        serialized = exp.dump_dict()
        deserialized = tmux.TmuxExperimentSpec.load_dict(_TEST_DUMP)
        self.assertDictEqual(deserialized.dump_dict(), serialized)


if __name__ == '__main__':
    unittest.main()
