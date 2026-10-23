"""Deterministic strategy comparison; no database or score-weight changes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine.monthly_processor import process_month_for_player, _amortized_emi, household_expenses
from engine.scoring import score_player_snapshot, liquidity_component
from engine.investment_engine import add_investment_lot, empty_portfolio, portfolio_value
from models.constants import LOAN_INTEREST_RATE
from tools.seed_content import events_data

STRATEGIES = {
    'A: High risk': (0.85, 0, 0, 0.15),
    'B: Strong emergency fund': (0.25, 0, 0.65, 0.10),
    'C: Cash heavy': (0, 0.10, 0, 0.90),
    'D: Debt and investment': (0.85, 0.05, 0, 0.10),
    'E: Balanced': (0.45, 0.20, 0.25, 0.10),
    'F: Repeated emergency borrowing': (1, 0, 0, 0),
}

INVESTMENT_STRATEGIES = {
    'G: Liquid investment reserve': {'liquid_fund': 0.35},
    'H: Diversified long-term': {'index_fund': 0.20, 'balanced_advantage_fund': 0.20},
    'I: Locked retirement': {'ppf': 0.20, 'nps': 0.20},
    'J: Term ladder': {'bank_fd_3m': 0.20, 'treasury_bill_6m': 0.20},
}


def simulate(name, weights, content_stress=True, investment_weights=None):
    state = {'user_id': 'strategy-player', 'month': 1, 'cash': 100000,
             'stocks': 0, 'gold': 0, 'emergency_fund': 0, 'loans': 0,
             'lifestyle_type': 'city', 'bike_status': False, 'bike_lock_in_months': 0,
             'discipline_score': 100, 'status': 'waiting', 'insurance_plan': 'none',
             'spouse_archetype': 'single', 'spouse_satisfaction': 60,
             'investment_portfolio': empty_portfolio(),
             'household_expense_modifier': 0}
    loans, history, next_id = [], [], 1
    for month in range(1, 13):
        if month > 1:
            result = process_month_for_player(
                state, month, [e for e in events_data if e['month'] == month] if content_stress else [],
                [l for l in loans if l['status'] == 'active'], [],
                auto_events=False, auto_market=False,
                market_scenario={'stock_pct': -0.06 if month in (5, 9) else 0.04,
                                 'gold_pct': 0.015, 'source': 'admin',
                                 'name': 'Common authored path', 'reason': 'Strategy comparison'})
            state = result['updated_state']
            for update in result['loan_updates']:
                next(l for l in loans if l['id'] == update['id']).update(update)
            for loan in result['new_loans']:
                loans.append(dict(loan, id=next_id))
                next_id += 1
        if name.startswith('D:') and month == 2:
            amount, term = 120000, 12
            loans.append({'id': next_id, 'user_id': state['user_id'], 'principal': amount,
                          'current_amount': amount, 'interest_rate': LOAN_INTEREST_RATE,
                          'month_taken': month, 'term_months': term, 'loan_type': 'player',
                          'emi': round(_amortized_emi(amount, LOAN_INTEREST_RATE, term), 2),
                          'status': 'active'})
            next_id += 1
            state['cash'] += amount
            state['loans'] += amount
        available = state['cash']
        investment_weights = investment_weights or {}
        total_investment_weight = sum(investment_weights.values())
        if total_investment_weight > 0.8:
            raise ValueError('Investment strategy may allocate at most 80% per month')
        for product_key, weight in investment_weights.items():
            amount = round(available * weight, 2)
            if amount > 0:
                state['investment_portfolio'] = add_investment_lot(
                    state['investment_portfolio'], product_key, amount, month)
                state['cash'] -= amount
        available = state['cash']
        legacy_weight_scale = 1 - total_investment_weight
        for key, weight in zip(('stocks', 'gold', 'emergency_fund'), weights[:3]):
            allocation = round(available * weight * legacy_weight_scale, 2)
            state[key] += allocation
            state['cash'] -= allocation
        state['cash'] = round(state['cash'], 2)
        state.update(score_player_snapshot(state))
        history.append(dict(state))
    expense = household_expenses(state, 12)['adjusted_living']
    return {'strategy': name, 'net_worth': state['net_worth'],
            'cash': state['cash'], 'emergency_fund': state['emergency_fund'],
            'investment_value': round(portfolio_value(state['investment_portfolio']), 2),
            'liquidity_months': round(state['emergency_fund'] / expense, 3),
            'liquidity_component': round(liquidity_component(state['emergency_fund'], expense), 2),
            'debt': state['loans'], 'risk_score': state['risk_level'],
            'discipline': state['discipline_score'], 'financial_health_score': state['financial_health_score'],
            'auto_loans': sum(l.get('loan_type') == 'auto' for l in loans), 'history': history}


def run(content_stress=True):
    results = sorted((simulate(name, weights, content_stress) for name, weights in STRATEGIES.items()),
                     key=lambda x: (-x['financial_health_score'], -x['net_worth']))
    for rank, result in enumerate(results, 1):
        result['rank'] = rank
    return results


def run_investments(content_stress=True):
    results = sorted((simulate(name, (0.45, 0.20, 0.25, 0.10), content_stress, allocation)
                      for name, allocation in INVESTMENT_STRATEGIES.items()),
                     key=lambda x: (-x['financial_health_score'], -x['net_worth']))
    for rank, result in enumerate(results, 1):
        result['rank'] = rank
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    results = {'baseline': run(False), 'content_stress': run(True),
               'investment_baseline': run_investments(False),
               'investment_content_stress': run_investments(True)}
    if args.output:
        args.output.write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps({scenario: [{k: v for k, v in r.items() if k != 'history'} for r in rows]
                      for scenario, rows in results.items()}, indent=2))
