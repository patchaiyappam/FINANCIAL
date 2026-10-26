// Family offers use public financial profiles; no paid trait reveals.
function renderFamilyOffers(section, offers, player, game) {
    const status = document.getElementById('marriageStatus');
    const terms = document.getElementById('marriageTerms');
    const skip = document.getElementById('staySingleBtn');
    const grid = document.getElementById('candidatesGrid');
    const month = offers.marriage_month;
    const starts = month + 1;
    const selected = offers.spouse_options.find(o => o.id === player.spouse_archetype);
    const ready = player.month === month && game.marriage_round_active && !player.spouse_archetype;
    const locked = player.status === 'waiting' || game.game_status !== 'active';
    section.style.display = 'block';
    section.classList.remove('glass-card');
    section.style.borderTop = '1px solid var(--border-glass)';
    section.style.paddingTop = '1.5rem';
    section.style.scrollMarginTop = '160px';
    grid.style.gridTemplateColumns = 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))';
    grid.replaceChildren();
    skip.hidden = !ready;
    skip.disabled = locked;
    terms.textContent = '';
    if (player.spouse_archetype === 'single') {
        status.textContent = 'You skipped marriage. Your income and expenses remain your own for this game.';
        return;
    }
    if (selected) {
        status.textContent = 'Married: ' + selected.name + '. Monthly income and expenses ' +
            (player.month < starts ? 'begin in Month ' + starts + '.' : 'are included in your household finances.');
    } else if (player.month < month) {
        status.textContent = 'Your family will introduce potential spouses in Month ' + month + '. Marriage is optional.';
        return;
    } else if (player.month > month) {
        status.textContent = 'The marriage round has passed. No spouse was selected.';
        return;
    } else if (!game.marriage_round_active) {
        status.textContent = 'Waiting for the host to open family marriage offers for Month ' + month + '.';
        terms.textContent = 'Your host can open the marriage round from Admin Controls.';
        return;
    } else {
        status.textContent = locked ? 'Offers are available. Your turn is locked or the game is paused.' :
            'Your family has decided it is time to discuss marriage. The month is on hold: meet the candidates, compare their finances, and choose a spouse or stay single.';
    }
    terms.textContent = 'Monthly income and expenses start in Month ' + starts +
        '. Wedding cost: ' + formatINR(offers.wedding_cost) +
        ' once, paid now. Existing spouse assets and debts join the household immediately. Your choice lasts for this game.';
    for (const option of selected ? [selected] : offers.spouse_options) {
        const card = document.createElement('article');
        card.className = 'choice-card';
        card.style.cssText = 'padding:1.25rem;border-radius:8px;min-width:0;display:flex;flex-direction:column;gap:0.75rem;overflow-wrap:anywhere;';
        const heading = document.createElement('h3');
        heading.style.cssText = 'font-size:1.1rem;margin:0;';
        heading.textContent = option.name;
        card.append(heading);
        const description = document.createElement('p');
        description.textContent = option.description || '';
        description.style.margin = '0';
        card.append(description);
        const hasFigures = [option.income, option.expense, option.assets, option.debt].every(Number.isFinite);
        const details = document.createElement('dl');
        details.style.cssText = 'margin:0;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:0.65rem;';
        const values = hasFigures ? [
            ['Monthly income', formatINR(option.income)],
            ['Monthly expenses', formatINR(option.expense)],
            ['Net each month', (option.income >= option.expense ? '+' : '-') + formatINR(Math.abs(option.income - option.expense))],
            ['Existing assets', formatINR(option.assets)],
            ['Existing debts', formatINR(option.debt)],
            ['Net worth joining you', formatINR(option.assets - option.debt)]
        ] : [['Profile unavailable', 'Host update needed']];
        for (const [label, value] of values) {
            const dt = document.createElement('dt');
            const dd = document.createElement('dd');
            dt.textContent = label;
            dd.textContent = value;
            dd.style.cssText = 'margin:0;text-align:right;font-weight:600;';
            details.append(dt, dd);
        }
        card.append(details);
        if (!selected) {
            const button = document.createElement('button');
            button.className = 'btn-glow';
            button.style.cssText = 'margin-top:auto;white-space:normal;min-height:44px;';
            const affordable = Number(player.cash) >= offers.wedding_cost;
            button.textContent = !hasFigures ? 'Waiting for profile' : affordable ? 'Marry ' + option.name : 'Need ' + formatINR(offers.wedding_cost) + ' cash';
            button.disabled = locked || !affordable || !hasFigures;
            button.addEventListener('click', () => window.proposeMarriage(option.id));
            card.append(button);
        }
        grid.append(card);
    }
}
