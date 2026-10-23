import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from local_database import LocalDatabase, ROOT

UID = '11111111-1111-1111-1111-111111111111'


@unittest.skipUnless((ROOT / '.test-runtime/node_modules/@electric-sql/pglite').exists(),
                     'Install the isolated PGlite test runtime')
class RuntimeDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = LocalDatabase()
        try:
            cls.db.install()
        except Exception:
            cls.db.close()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def setUp(self):
        self.db.call('TRUNCATE auth.users CASCADE', exec=True)
        self.db.call("UPDATE game_control SET current_month=4, game_status='active', marriage_round_active=true, negotiation_enabled=true", exec=True)
        self.db.call('INSERT INTO auth.users(id,email) VALUES ($1,$2)', [UID, 'test@local'])
        self.db.table('player_state').insert({'user_id': UID, 'month': 4, 'cash': 100000}).execute()

    def txn(self, **changes):
        args = dict(p_user_id=UID, p_month=4, p_action_key=None, p_require_cash=None,
                    p_deltas={}, p_sets={}, p_clamp_satisfaction=False,
                    p_recompute_networth=True, p_loan_inserts=[], p_loan_updates=[],
                    p_expected_investment_portfolio=None)
        args.update(changes)
        return self.db.rpc('player_apply_atomic', args).execute().data

    def test_fresh_schema_and_repeat_install_preserve_data(self):
        self.db.install()
        self.assertEqual(float(self.db.table('player_state').select().execute().data[0]['cash']), 100000)
        self.assertEqual(len(self.db.table('case_study').select().execute().data), 1)
        tables = {r['table_name'] for r in self.db.call("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")['rows']}
        for name in ('player_negotiations', 'spouse_proposals', 'spouse_dialogue', 'player_month_allocations', 'market_scenarios'):
            self.assertIn(name, tables)

    def test_runtime_tables_and_rpcs_exist_with_rls(self):
        import ast
        tables, functions = set(), set()
        for source in (ROOT / 'backend').rglob('*.py'):
            if 'tests' in source.parts:
                continue
            for node in ast.walk(ast.parse(source.read_text(encoding='utf-8-sig'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in ('table', 'rpc') and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    (tables if node.func.attr == 'table' else functions).add(node.args[0].value)
        actual = self.db.call("SELECT relname, relrowsecurity FROM pg_class JOIN pg_namespace n ON n.oid=relnamespace WHERE n.nspname='public' AND relkind='r'")['rows']
        protected = {r['relname'] for r in actual if r['relrowsecurity']}
        self.assertFalse(tables - protected, tables - protected)
        installed = {r['proname'] for r in self.db.call("SELECT proname FROM pg_proc JOIN pg_namespace n ON n.oid=pronamespace WHERE n.nspname='public'")['rows']}
        self.assertFalse(functions - installed, functions - installed)

    def test_atomic_claim_rolls_back_with_failed_child_insert(self):
        with self.assertRaises(RuntimeError):
            self.txn(p_action_key='failure', p_deltas={'cash': -1000},
                     p_loan_inserts=[{'principal': 'invalid'}])
        self.assertEqual(float(self.txn(p_action_key='failure', p_deltas={'cash': -1000})['cash']), 99000)
        with self.assertRaisesRegex(RuntimeError, 'DUPLICATE_ACTION'):
            self.txn(p_action_key='failure', p_deltas={'cash': -1000})

    def test_initial_allocation_log_failure_is_retryable(self):
        # Reproduce the missing deployed RPC, then install the repair twice.
        self.db.call('DROP FUNCTION public.initialize_player(jsonb)', exec=True)
        repair = (ROOT / 'repair_initialize_player.sql').read_text(encoding='utf-8')
        self.db.call(repair, exec=True)
        self.db.call(repair, exec=True)
        self.assertEqual(float(self.db.table('player_state').select().execute().data[0]['cash']), 100000)
        self.db.table('player_state').delete().eq('user_id', UID).execute()
        self.db.table('game_control').update({'current_month': 1}).eq('id', 1).execute()
        initial = {'user_id': UID, 'cash': 100000, 'stocks': 0, 'gold': 0,
                   'emergency_fund': 0, 'lifestyle_type': 'city', 'bike_status': False,
                   'bike_lock_in_months': 0, 'net_worth': 100000,
                   'risk_level': 20, 'financial_health_score': 50}
        self.db.call("""CREATE FUNCTION fail_initial_log() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected log failure'; END; $$;
            CREATE TRIGGER fail_initial_log BEFORE INSERT ON player_month_log
            FOR EACH ROW EXECUTE FUNCTION fail_initial_log();""", exec=True)
        try:
            with self.assertRaisesRegex(RuntimeError, 'injected log failure'):
                self.db.rpc('initialize_player', {'p_state': initial}).execute()
            self.assertEqual(self.db.table('player_state').select().execute().data, [])
            self.assertEqual(self.db.table('player_month_actions').select().execute().data, [])
        finally:
            self.db.call('DROP TRIGGER fail_initial_log ON player_month_log; DROP FUNCTION fail_initial_log();', exec=True)
        self.assertEqual(self.db.rpc('initialize_player', {'p_state': initial}).execute().data['status'], 'waiting')

    def test_reveal_charge_and_record_are_atomic(self):
        for trait in ('income', 'expense_mod', 'assets'):
            result = self.txn(p_sets={'reveal': {'archetype_id': 'saver', 'trait_key': trait}})
            self.assertEqual(float(result['reveal_cost']), 0)
        args = {'reveal': {'archetype_id': 'anchor', 'trait_key': 'income'}}
        self.assertEqual(float(self.txn(p_sets=args)['cash']), 95000)
        self.assertEqual(float(self.txn(p_sets=args)['cash']), 95000)
        with self.assertRaises(RuntimeError):
            self.txn(p_sets={'reveal': {'archetype_id': 'missing', 'trait_key': 'income'}})
        self.assertEqual(float(self.txn()['cash']), 95000)

    def test_gate_rejects_unlocked_players_and_single_is_valid(self):
        result = self.db.rpc('begin_month_transition', {'p_expected_month': 4}).execute().data
        self.assertFalse(result['ready'])
        self.assertEqual(result['unlocked_count'], 1)
        self.txn(p_action_key='marry', p_sets={'spouse_archetype': 'single'})
        self.txn(p_action_key='alloc:4')
        self.txn(p_sets={'status': 'waiting'})
        self.assertTrue(self.db.rpc('begin_month_transition', {'p_expected_month': 4}).execute().data['ready'])
        with self.assertRaisesRegex(RuntimeError, 'TURN_NOT_PLAYABLE'):
            self.txn(p_sets={'insurance_plan': 'none'})

    def test_absent_unstarted_players_do_not_block_but_started_players_do(self):
        for index, username in enumerate(('cb22s612706', 'manoj', 'patchai2004'), 2):
            uid = f'00000000-0000-0000-0000-{index:012d}'
            self.db.call('INSERT INTO auth.users(id,email) VALUES ($1,$2)',
                         [uid, username + '@event.local'])
        self.db.table('game_control').update({'current_month': 1}).eq('id', 1).execute()
        self.db.table('player_state').update({'month': 1, 'status': 'active'}).eq('user_id', UID).execute()
        repair = (ROOT / 'mark_absent_players.sql').read_text(encoding='utf-8')
        self.db.call(repair, exec=True)
        self.db.call(repair, exec=True)
        gate = self.db.rpc('begin_month_transition', {'p_expected_month': 1}).execute().data
        self.assertFalse(gate['ready'])
        self.assertEqual(gate['unlocked_count'], 1)
        self.assertEqual(gate['unallocated_count'], 0)
        self.db.table('player_state').update({'status': 'waiting'}).eq('user_id', UID).execute()
        self.assertTrue(self.db.rpc('begin_month_transition', {'p_expected_month': 1}).execute().data['ready'])
        self.assertEqual(len(self.db.table('users').select().execute().data), 4)
        self.assertEqual(float(self.db.table('player_state').select().execute().data[0]['cash']), 100000)
        self.db.table('game_control').update({'game_status': 'active'}).eq('id', 1).execute()
        self.db.table('player_month_actions').delete().eq('month', 0).execute()
        gate = self.db.rpc('begin_month_transition', {'p_expected_month': 1}).execute().data
        self.assertEqual(gate['unallocated_count'], 3)

    def test_event_category_and_rpc_permissions(self):
        row = self.db.table('events').insert({'month': 4, 'category': 'medical', 'event_name': 'Medical', 'value': -1000}).execute().data[0]
        self.assertEqual(row['category'], 'medical')
        grants = self.db.call("SELECT has_function_privilege('authenticated', 'public.player_apply_atomic(uuid,int,text,numeric,jsonb,jsonb,boolean,boolean,jsonb,jsonb,jsonb)', 'EXECUTE') AS allowed")['rows']
        self.assertFalse(grants[0]['allowed'])

    def test_negotiation_result_failure_rolls_back_money_and_claim(self):
        self.txn(p_sets={'spouse_archetype': 'saver'})
        pending = self.db.table('player_negotiations').insert({
            'user_id': UID, 'month': 4, 'round': 1, 'intent': 'ACCEPT_PROPOSAL',
            'params': {}, 'raw_text': 'yes'}).execute().data[0]
        result = {'id': pending['id'], 'round': 1, 'intent': 'ACCEPT_PROPOSAL',
                  'params': {}, 'outcome': 'accepted_full', 'rule_input': {'ask': 1000},
                  'rule_output': {'effects': {'cash': -1000}}}
        self.db.call("""CREATE FUNCTION fail_negotiation() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'injected failure'; END; $$;
            CREATE TRIGGER fail_negotiation BEFORE UPDATE ON player_negotiations
            FOR EACH ROW EXECUTE FUNCTION fail_negotiation();""", exec=True)
        try:
            with self.assertRaisesRegex(RuntimeError, 'injected failure'):
                self.txn(p_action_key='negotiate:4:1', p_deltas={'cash': -1000},
                         p_sets={'negotiation': result})
            self.assertEqual(float(self.txn()['cash']), 100000)
        finally:
            self.db.call('DROP TRIGGER fail_negotiation ON player_negotiations; DROP FUNCTION fail_negotiation();', exec=True)
        self.assertEqual(float(self.txn(p_action_key='negotiate:4:1', p_deltas={'cash': -1000}, p_sets={'negotiation': result})['cash']), 99000)
        self.assertTrue(self.db.table('player_negotiations').select().execute().data[0]['confirmed'])

    def test_monthly_persists_every_engine_field_and_new_loan_terms(self):
        from engine.monthly_processor import process_month_for_player
        self.txn(p_sets={'spouse_archetype': 'saver', 'insurance_plan': 'basic'})
        self.db.table('player_state').update({'spouse_satisfaction': 0,
            'household_expense_modifier': -1200, 'status': 'waiting', 'cash': 0}).eq('user_id', UID).execute()
        player = self.db.table('player_state').select().execute().data[0]
        self.db.rpc('begin_month_transition', {'p_expected_month': 4}).execute()
        result = process_month_for_player(player, 5, [{
            'event_name': 'Emergency', 'category': 'medical', 'event_type': 'fixed',
            'impact_target': 'cash', 'value': -300000}], [], [], auto_events=False, auto_market=False)
        expected = result['updated_state']
        args = {'p_updates_player_state': [expected], 'p_updates_loans': [],
                'p_inserts_loans': result['new_loans'], 'p_inserts_logs': [{
                    'user_id': UID, 'month': 5, 'starting_cash': 0,
                    'ending_cash': expected['cash'], 'net_worth': expected['net_worth'], 'summary': 'test'}],
                'p_next_month': 5}
        self.db.rpc('process_month_atomically', args).execute()
        actual = self.db.table('player_state').select().execute().data[0]
        for key, value in expected.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.assertAlmostEqual(float(actual[key]), value, places=2, msg=key)
            else:
                self.assertEqual(actual[key], value)
        self.assertEqual(actual['spouse_satisfaction'], '0')
        loan = self.db.table('player_loans').select().execute().data[0]
        self.assertEqual(loan['loan_type'], 'auto')
        self.assertGreater(float(loan['emi']), 0)
        self.assertGreater(loan['term_months'], 0)
        self.assertTrue(any('Insurance' in line or 'Insurance' in line.title() for line in result['event_log']))


if __name__ == '__main__':
    unittest.main()
