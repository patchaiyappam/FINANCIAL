"""Real Flask routes and PostgreSQL SQL, with local auth and offline AI only."""
import importlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
isolated_python = ROOT / '.test-runtime/python'
try:
    (isolated_python / 'flask/__init__.py').read_bytes()
except OSError:
    # Use the active interpreter's dependencies when the optional bundled
    # runtime exists but is inaccessible in this checkout.
    pass
else:
    sys.path.insert(0, str(isolated_python))
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'backend/tests'))
from local_database import LocalDatabase
from engine.monthly_processor import process_month_for_player
from engine.market_engine import resolve_market_scenario
from engine.scoring import score_player_snapshot
from models.constants import WEDDING_COST, ARCHETYPES, SPOUSE_BASE_EXPENSE
from tools.seed_content import events_data

UID = '11111111-1111-1111-1111-111111111111'


@unittest.skipUnless((ROOT / '.test-runtime/node_modules/@electric-sql/pglite').exists(),
                     'Install isolated database and Python test dependencies')
class ApiLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flask import Flask
        cls.db = LocalDatabase()
        cls.db.install()
        # Exercise the deployment repair before the complete game lifecycle.
        for signature in (
            'initialize_player(jsonb)', 'begin_month_transition(integer)',
            'process_month_atomically(json,json,json,json,integer)',
            'finish_game_atomically(jsonb)',
        ):
            cls.db.call('DROP FUNCTION public.' + signature, exec=True)
        repair = (ROOT / 'repair_game_functions.sql').read_text(encoding='utf-8')
        cls.db.call(repair, exec=True)
        cls.db.call(repair, exec=True)
        cls.module_patch = patch.dict(sys.modules, {'supabase_client': SimpleNamespace(supabase=cls.db)})
        cls.module_patch.start()
        cls.patches = []
        for name in ('services.game_service', 'services.auth_service', 'routes.player_routes', 'routes.admin_routes'):
            mod = importlib.import_module(name)
            p = patch.object(mod, 'supabase', cls.db)
            p.start()
            cls.patches.append(p)
        from routes import player_routes, admin_routes
        from services import auth_service, ai_service
        for mod, key, value in ((player_routes, 'get_user_id', lambda request: UID),
                                (auth_service, 'get_user_id', lambda request: UID),
                                (auth_service, 'is_admin_user', lambda uid: True),
                                (ai_service, 'ANTHROPIC_KEY', '')):
            p = patch.object(mod, key, value)
            p.start()
            cls.patches.append(p)
        cls.app = Flask(__name__)
        cls.app.testing = True
        cls.app.register_blueprint(player_routes.player_bp)
        cls.app.register_blueprint(admin_routes.admin_bp)
        cls.client = cls.app.test_client()

    @classmethod
    def tearDownClass(cls):
        for p in reversed(cls.patches):
            p.stop()
        cls.module_patch.stop()
        cls.db.close()

    def setUp(self):
        self.db.call('TRUNCATE auth.users CASCADE; TRUNCATE events, market_scenarios, spouse_proposals, spouse_dialogue;', exec=True)
        self.db.call('INSERT INTO auth.users(id,email) VALUES ($1,$2)', [UID, 'dryrun@local'])
        self.post('/start-game')
        self.db.table('game_control').update({'auto_events': False, 'auto_market': False,
                                               'negotiation_enabled': False}).eq('id', 1).execute()

    def post(self, url, body=None, status=200):
        response = self.client.post(url, json=body or {})
        self.assertEqual(response.status_code, status, (url, response.get_json()))
        return response.get_json()

    def state(self):
        return self.db.table('player_state').select().eq('user_id', UID).execute().data[0]

    def allocate_first(self):
        return self.post('/allocate', {'misc': 65000, 'stocks': 15000, 'gold': 5000,
                                      'emergency_fund': 15000, 'lifestyle_type': 'outer'})

    def test_admin_gate_counts_players_without_initial_allocation(self):
        result = self.post('/next-month', {'expected_month': 1}, 409)
        self.assertEqual(result['unallocated_count'], 1)
        self.assertEqual(self.db.table('game_control').select().execute().data[0]['game_status'], 'active')

    def test_month_failure_restores_active(self):
        self.allocate_first()
        with patch('routes.admin_routes.get_admin_events_for_month', side_effect=RuntimeError('test failure')):
            self.post('/next-month', {'expected_month': 1}, 500)
        self.assertEqual(self.db.table('game_control').select().execute().data[0]['game_status'], 'active')
        self.assertEqual(self.state()['month'], 1)

    def test_leaderboard_score_first_and_net_worth_tiebreak(self):
        for suffix, score, worth in ((1, 70, 1000), (2, 60, 999999), (3, 70, 2000)):
            uid = f'22222222-2222-2222-2222-{suffix:012d}'
            self.db.call('INSERT INTO auth.users(id,email) VALUES ($1,$2)', [uid, f'{suffix}@local'])
            self.db.table('player_state').insert({'user_id': uid,
                'financial_health_score': score, 'net_worth': worth}).execute()
        # Ranking uses freshly calculated snapshots rather than stale stored
        # score/net-worth columns; isolate the ordering contract here.
        snapshots = {
            1: {'financial_health_score': 70, 'net_worth': 1000},
            2: {'financial_health_score': 60, 'net_worth': 999999},
            3: {'financial_health_score': 70, 'net_worth': 2000},
        }
        with patch('engine.scoring.score_player_snapshot', side_effect=lambda row: snapshots[int(row['user_id'][-1])]):
            board = self.client.get('/leaderboard').get_json()
        self.assertEqual([int(row['user_id'][-12:]) for row in board], [3, 1, 2])

    def test_event_creation_category_and_case_study_expenses(self):
        from models.constants import LIFESTYLE_COSTS
        self.post('/event', {'month': 3, 'event_name': 'Medical', 'event_type': 'fixed',
                            'impact_target': 'cash', 'value': -1000, 'category': 'medical'})
        self.assertEqual(self.db.table('events').select().execute().data[0]['category'], 'medical')
        self.assertEqual(self.client.get('/case-study').get_json()['lifestyles'], LIFESTYLE_COSTS)

    def test_investment_products_persist_across_monthly_flow_and_sales(self):
        self.post('/allocate', {
            'rent': -100000, 'misc': 200000, 'bike_status': True,
            'bike_down_payment': 0
        }, 400)
        self.post('/allocate', {'misc': 'NaN'}, 400)
        self.post('/allocate', {
            'misc': 50000, 'stocks': 10000, 'gold': 5000, 'emergency_fund': 10000,
            'bank_fd_3m': 5000, 'index_fund': 5000, 'arbitrage_fund': 5000,
            'gold_etf': 5000, 'business_venture': 5000, 'lifestyle_type': 'outer'
        })
        initial = self.state()['investment_portfolio']
        self.assertAlmostEqual(float(initial['bank_fd_3m'][0]['value']), 5000)
        self.assertAlmostEqual(float(initial['business_venture'][0]['principal']), 5000)

        self.post('/next-month', {'expected_month': 1})
        after_market = self.state()
        self.assertIn('gold_etf', after_market['investment_portfolio'])
        self.assertNotEqual(after_market['investment_portfolio'], {})
        starting_cash = float(after_market['cash'])
        self.post('/allocate-month', {'business_venture': 2000, 'gold_etf': 3000,
                                     'emergency_fund': 1000})
        allocated = self.state()
        self.assertAlmostEqual(float(allocated['cash']), starting_cash - 6000, places=2)
        self.assertEqual(len(allocated['investment_portfolio']['business_venture']), 2)

        old_gold_value = sum(float(x['value']) for x in allocated['investment_portfolio']['gold_etf'])
        quote = self.post('/investment-sale-quote', {'product': 'gold_etf', 'amount': 1000})
        self.assertAlmostEqual(float(quote['penalty']), 0)
        self.assertAlmostEqual(float(quote['cash_proceeds']), 1000)
        sold = self.post('/sell-investment', {'product': 'gold_etf', 'amount': 1000,
                                              'request_id': 'sale-request-20261020'})
        after_sale = self.state()
        new_gold_value = sum(float(x['value']) for x in after_sale['investment_portfolio']['gold_etf'])
        self.assertAlmostEqual(old_gold_value - new_gold_value, 1000, places=2)
        self.assertAlmostEqual(float(after_sale['cash']), float(allocated['cash']) + sold['cash_proceeds'], places=2)
        self.assertGreaterEqual(float(after_sale['net_worth']), 0)
        duplicate = self.client.post('/sell-investment', json={
            'product': 'gold_etf', 'amount': 1000, 'request_id': 'sale-request-20261020'
        })
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(self.state()['investment_portfolio'], after_sale['investment_portfolio'])
        dashboard = self.client.get('/dashboard').get_json()
        self.assertAlmostEqual(float(dashboard['player']['net_worth']), float(after_sale['net_worth']), places=2)
        self.assertAlmostEqual(float(dashboard['investment_summary']['value']),
                               sum(float(lot['value']) for lots in after_sale['investment_portfolio'].values() for lot in lots), places=2)

    def test_month_twelve_next_month_asset_sale_is_rejected(self):
        self.allocate_first()
        self.db.table('game_control').update({'current_month': 12}).eq('id', 1).execute()
        self.db.table('player_state').update({'month': 12, 'status': 'active', 'stocks': 1000}).eq('user_id', UID).execute()
        response = self.client.post('/sell', json={'asset': 'stocks', 'amount': 500})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(float(self.state()['stocks']), 1000)
        self.assertEqual(self.db.table('player_sales').select().execute().data, [])

    def test_invalid_offers_do_not_exhaust_function_rounds(self):
        self.allocate_first()
        self.db.table('game_control').update({'current_month': 7, 'negotiation_enabled': True}).eq('id', 1).execute()
        self.db.table('player_state').update({'month': 7, 'status': 'active', 'spouse_archetype': 'saver', 'cash': 1000}).eq('user_id', UID).execute()
        for _ in range(4):
            interpreted = self.post('/negotiate', {'message': 'yes'})
            result = self.post('/negotiate/commit', {'intent': interpreted['intent'], 'params': interpreted['params']})
            self.assertEqual(result['outcome'], 'invalid')
            self.assertEqual(self.client.get('/dashboard').get_json()['negotiation']['round'], 1)
            self.assertEqual(float(self.state()['cash']), 1000)
        interpreted = self.post('/negotiate', {'message': 'no'})
        self.post('/negotiate/commit', {'intent': interpreted['intent'], 'params': interpreted['params']})
        self.post('/allocate-month', {})
        self.post('/lock-turn')

    def test_full_twelve_month_lifecycle(self):
        traces = []
        self.db.table('events').insert(events_data).execute()
        for month in range(2, 13):
            self.db.table('market_scenarios').insert({
                'month': month, 'name': f'Dry run {month}', 'reason': 'Deterministic fixture',
                'stock_pct': -0.06 if month in (5, 9) else 0.025,
                'gold_pct': 0.015 if month in (5, 9) else 0.005}).execute()
        self.allocate_first()
        self.post('/allocate', {'misc': 100000}, 400)
        traces.append({'month': 1, 'state': self.state()})
        for month in range(2, 13):
            before = self.state()
            loans = self.db.table('player_loans').select().eq('user_id', UID).eq('status', 'active').execute().data
            sales = self.db.table('player_sales').select().eq('user_id', UID).eq('month_to_credit', month).execute().data
            events = self.db.table('events').select().eq('month', month).execute().data
            market = self.db.table('market_scenarios').select().eq('month', month).execute().data[0]
            expected = process_month_for_player(before, month, events, loans, sales,
                                                 auto_events=False, auto_market=False,
                                                 market_scenario=resolve_market_scenario(month, market, False))
            self.post('/next-month', {'expected_month': month - 1})
            actual = self.state()
            for key, value in expected['updated_state'].items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    self.assertAlmostEqual(float(actual[key]), value, places=2, msg=f'{month}: {key}')
                else:
                    self.assertEqual(actual[key], value, f'{month}: {key}')
            self.post('/next-month', {'expected_month': month}, 409)
            if month == 2:
                cash = float(self.state()['cash'])
                self.post('/insurance', {'plan': 'basic'})
                self.post('/insurance', {'plan': 'basic'})
                self.assertEqual(float(self.state()['cash']), cash)
                self.post('/sell', {'asset': 'stocks', 'amount': 1000})
            if month == 3:
                self.post('/loan', {'amount': 20000, 'term_months': 6})
                self.post('/loan', {'amount': 20000, 'term_months': 6}, 400)
            if month == 6:
                self.assertTrue(self.client.get('/game-status').get_json()['marriage_round_active'])
                self.post('/allocate-month', {})
                self.post('/lock-turn', status=409)
                with self.assertRaisesRegex(RuntimeError, 'MARRIAGE_DECISION_REQUIRED'):
                    self.db.rpc('player_apply_atomic', {'p_user_id': UID, 'p_month': month, 'p_action_key': None, 'p_require_cash': 0, 'p_deltas': {}, 'p_sets': {'status': 'waiting'}, 'p_clamp_satisfaction': False, 'p_recompute_networth': True, 'p_loan_inserts': [], 'p_loan_updates': [], 'p_expected_investment_portfolio': None}).execute()
                for trait in ('income', 'expense_mod', 'assets'):
                    self.post('/courtship/reveal', {'archetype_id': 'saver', 'trait_key': trait})
                dashboard = self.client.get('/dashboard').get_json()
                self.assertEqual(dashboard['courtship']['wedding_cost'], WEDDING_COST)
                self.assertIn(str(ARCHETYPES['saver']['income'] // 1000), dashboard['courtship']['reveals'][0]['revealed_value'])
                before_marriage = float(self.state()['cash'])
                self.post('/courtship/marry', {'choice': 'saver'})
                arc = ARCHETYPES['saver']
                self.assertAlmostEqual(float(self.state()['cash']), before_marriage - WEDDING_COST)
                self.post('/courtship/marry', {'choice': 'anchor'}, 400)

            if month == 7:
                proposal = self.client.get('/dashboard').get_json()['negotiation']['proposal']
                self.assertEqual(proposal['month'], 7)
                self.assertIn('function', proposal['title'].lower())
                self.post('/allocate-month', {})
                self.post('/lock-turn', status=409)
                interpreted = self.post('/negotiate', {'message': 'no' if month == 8 else 'yes'})
                before_commit = self.state()
                result = self.post('/negotiate/commit', {'intent': interpreted['intent'], 'params': interpreted['params']})
                committed = self.db.table('player_negotiations').select().eq('month', month).eq('confirmed', True).execute().data
                self.assertEqual(len(committed), 1)
                self.assertEqual(committed[0]['outcome'], 'refused' if month == 8 else 'accepted_full', f'Month {month}')
                self.assertAlmostEqual(float(self.state()['cash']), float(before_commit['cash']) - (0 if month == 8 else proposal['ask']))
                self.post('/negotiate/commit', {'intent': interpreted['intent'], 'params': interpreted['params']}, 400)
            if month != 7:
                self.assertFalse(self.client.get('/dashboard').get_json()['negotiation']['active'])
            if float(self.state()['cash']) > 0 and month not in (6, 7):
                self.post('/allocate-month', {'stocks': 500, 'gold': 200, 'emergency_fund': 300}
                          if float(self.state()['cash']) >= 1000 else {})
            dashboard = self.client.get('/dashboard').get_json()
            self.assertIn('expenses', dashboard)
            self.post('/lock-turn')
            self.post('/insurance', {'plan': 'none'}, 400)
            traces.append({'month': month, 'state': self.state(), 'report': expected['event_log'],
                           'expenses': dashboard['expenses'], 'market': dashboard['market']})
        expected_final = score_player_snapshot(self.state())
        self.post('/next-month', {'expected_month': 12})
        self.assertEqual(self.db.table('game_control').select().execute().data[0]['game_status'], 'ended')
        self.assertEqual(float(self.state()['financial_health_score']), expected_final['financial_health_score'])
        self.post('/next-month', {'expected_month': 12}, 400)
        board = self.client.get('/leaderboard').get_json()
        self.assertEqual(board[0]['user_id'], UID)
        self.assertEqual(float(board[0]['financial_health_score']), expected_final['financial_health_score'])
        out = ROOT / '.test-runtime/dry_run.json'
        out.write_text(json.dumps({'months': traces, 'final': board}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
