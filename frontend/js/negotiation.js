// ============================================================================
// SPOUSE NEGOTIATION UI (ADR-014)
// ============================================================================
// Two-step by design, mirroring the backend: /negotiate INTERPRETS, the player
// CONFIRMS what she understood, then /negotiate/commit lets the rules engine
// decide. Nothing is spent on an interpretation the player has not seen.

let _negoPending = null;
let _negoState = null;

function renderNegotiation(n) {
    const sec = document.getElementById('negotiationSection');
    if (!sec) return;
    if (!n || !n.active) { sec.style.display = 'none'; return; }

    _negoState = n;
    sec.style.display = 'block';

    const p = n.proposal;
    document.getElementById('negoTitle').innerText = p.title;
    document.getElementById('negoDesc').innerText = p.description;
    document.getElementById('negoAsk').innerText = formatINR(p.ask);
    document.getElementById('negoEv').innerText = p.ev_note || '';
    document.getElementById('negoRound').innerText = `${n.round} / ${n.max_rounds}`;

    const sat = Math.round(n.satisfaction);
    document.getElementById('negoSatVal').innerText = sat;
    const bar = document.getElementById('negoSatBar');
    bar.style.width = sat + '%';
    // Colour tracks mood so the player reads the relationship at a glance.
    bar.style.background = sat >= 60 ? 'var(--gradient-success)'
                        : sat >= 35 ? 'var(--gradient-warning)'
                        : 'var(--gradient-danger)';

    if (n.round === 1) {
        document.getElementById('negoHint').innerText =
            'Type naturally. Name a number, or say yes, no, or later. She will not settle on the first reply — talk it through.';
    }

    const chat = document.getElementById('negoChat');
    if (chat && !chat.dataset.seeded) {
        chat.innerHTML = '';
        (n.history || []).forEach(h => {
            if (h.raw_text) addBubble(h.raw_text, 'you');
        });
        chat.dataset.seeded = '1';
    }
}

function addBubble(text, who) {
    const chat = document.getElementById('negoChat');
    if (!chat) return;
    const mine = who === 'you';
    const el = document.createElement('div');
    el.style.cssText = `display:flex; justify-content:${mine ? 'flex-end' : 'flex-start'}; margin-bottom:0.5rem;`;
    el.innerHTML = `<div style="max-width:78%; padding:0.55rem 0.85rem; border-radius:var(--radius-md);
        ${mine ? 'border-bottom-right-radius:4px; background:var(--gradient-primary); color:#fff;'
               : 'border-bottom-left-radius:4px; background:#e8f4fe; color:var(--text-primary);'}
        font-size:0.85rem; line-height:1.5;"></div>`;
    el.firstElementChild.textContent = text;
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
}

async function negotiateSend() {
    const input = document.getElementById('negoInput');
    const btn = document.getElementById('negoSend');
    const text = (input.value || '').trim();
    if (!text) return;

    btn.disabled = true;
    try {
        const res = await fetch(`${API_BASE_URL}/negotiate`, {
            method: 'POST', headers: await getAuthHeaders(),
            body: JSON.stringify({ message: text })
        });
        const d = await res.json();

        if (!res.ok) {
            // Ambiguous input is rejected, not guessed at — ask for a rewrite.
            addBubble(text, 'you');
            addBubble(d.error || 'Could not send that.', 'her');
            if (!d.needs_rephrase) showToast(d.error || 'Failed', 'error');
            input.value = '';
            btn.disabled = false;
            return;
        }

        addBubble(text, 'you');
        _negoPending = { intent: d.intent, params: d.params, message: text };
        document.getElementById('negoConfirmText').innerText = d.confirmation;
        document.getElementById('negoConfirm').style.display = 'block';
        document.getElementById('negoInputRow').style.display = 'none';
        input.value = '';
    } catch (e) {
        showToast('Failed to connect to server', 'error');
    }
    btn.disabled = false;
}

async function negotiateCommit() {
    if (!_negoPending) return;
    const yes = document.getElementById('negoConfirmYes');
    yes.disabled = true;
    try {
        const res = await fetch(`${API_BASE_URL}/negotiate/commit`, {
            method: 'POST', headers: await getAuthHeaders(),
            body: JSON.stringify(_negoPending)
        });
        const d = await res.json();
        if (!res.ok) { showToast(d.error || 'Failed', 'error'); document.getElementById('negoInputRow').style.display = 'flex'; }
        else {
            addBubble(d.spouse_line, 'her');
            if (d.resolved) {
                const good = ['accepted_full', 'accepted_counter'].includes(d.outcome);
                showToast(d.reason, good ? 'success' : 'info');
                if (window.fx && good && d.agreed_amount > 0) fx.confetti(40);
                if (window.fx && d.outcome === 'refused') fx.shake('negotiationSection');
                document.getElementById('negoInputRow').style.display = 'none';
                document.getElementById('negoHint').innerText = 'This month’s conversation is settled.';
            } else {
                document.getElementById('negoInputRow').style.display = 'flex';
            }
            document.getElementById('negoRound').innerText = `${Math.min(d.round + 1, d.max_rounds)} / ${d.max_rounds}`;
        }
        document.getElementById('negoConfirm').style.display = 'none';
        _negoPending = null;
        await loadDashboard();
    } catch (e) {
        showToast('Failed to connect to server', 'error');
    }
    yes.disabled = false;
}

document.addEventListener('DOMContentLoaded', () => {
    const send = document.getElementById('negoSend');
    if (!send) return;
    send.addEventListener('click', negotiateSend);
    document.getElementById('negoInput').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') negotiateSend();
    });
    document.getElementById('negoConfirmYes').addEventListener('click', negotiateCommit);
    document.getElementById('negoConfirmNo').addEventListener('click', () => {
        _negoPending = null;
        document.getElementById('negoConfirm').style.display = 'none';
        document.getElementById('negoInputRow').style.display = 'flex';
    });
});


window.renderNegotiation = renderNegotiation;
