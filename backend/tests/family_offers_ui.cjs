const { chromium } = require(process.env.PLAYWRIGHT_MODULE);
const fs = require('fs');
const path = require('path');
const assert = require('assert');
(async () => {
    const browser = await chromium.launch({headless: true, channel: process.env.PLAYWRIGHT_CHANNEL || 'chrome'});
    try {
        const page = await browser.newPage();
        const html = fs.readFileSync('frontend/dashboard.html', 'utf8')
            .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
            .replace(/<link[^>]*>/gi, '');
        await page.setContent(html);
        await page.addStyleTag({content: fs.readFileSync('frontend/css/style.css', 'utf8')});
        await page.addScriptTag({path: 'frontend/js/family-offers.js'});
        await page.evaluate(() => {
            window.formatINR = n => 'Rs ' + n.toLocaleString('en-IN');
            window.proposeMarriage = id => { window.chosen = id; };
            window.offers = {marriage_month: 6, wedding_cost: 25000, spouse_options: [
                {id:'saver', name:'The Saver', income:5000, expense:6500, assets:35000, debt:0},
                {id:'earner', name:'The Earner', income:16000, expense:13500, assets:5000, debt:0},
                {id:'investor', name:'The Investor', income:4000, expense:7500, assets:55000, debt:0},
                {id:'teacher', name:'The Teacher', income:6000, expense:7500, assets:37500, debt:0},
                {id:'healthcare', name:'The Healthcare Professional', income:11500, expense:11000, assets:22500, debt:0},
                {id:'anchor', name:'The Anchor', income:7000, expense:8500, assets:20000, debt:0}
            ]};
            window.render = (p = {}, g = {}) => renderFamilyOffers(
                document.getElementById('courtshipSection'), window.offers,
                {month:6, cash:50000, status:'active', ...p},
                {game_status:'active', marriage_round_active:true, ...g});
        });
        for (const width of [390, 1440]) {
            await page.setViewportSize({width, height:1000});
            await page.evaluate(() => render());
            assert.equal(await page.locator('#candidatesGrid article').count(), 6);
            await page.getByRole('button', {name:'Marry The Saver', exact:true}).click();
            assert.equal(await page.evaluate(() => window.chosen), 'saver');
            assert(await page.evaluate(() => {
                const section = document.getElementById('courtshipSection');
                return section.scrollWidth <= section.clientWidth + 1 &&
                    [...section.querySelectorAll('article')].every(e => e.scrollWidth <= e.clientWidth + 1);
            }));
            await page.locator('#courtshipSection').screenshot({path:path.join('.test-runtime', 'marriage-' + width + '.png')});
        }
        await page.evaluate(() => render({month:3}));
        assert((await page.locator('#marriageStatus').innerText()).includes('Month 6'));
        await page.evaluate(() => render({}, {marriage_round_active:false}));
        assert((await page.locator('#marriageStatus').innerText()).includes('Waiting'));
        await page.evaluate(() => render({spouse_archetype:'single'}));
        assert((await page.locator('#marriageStatus').innerText()).includes('skipped'));
        await page.evaluate(() => render({spouse_archetype:'saver'}));
        assert((await page.locator('#marriageStatus').innerText()).includes('Month 7'));
        await page.evaluate(() => render({status:'waiting'}));
        assert(await page.getByRole('button', {name:'Marry The Saver', exact:true}).isDisabled());
        await page.evaluate(() => render({cash:0}));
        assert(await page.locator('#candidatesGrid button').first().isDisabled());
        await page.addScriptTag({path: 'frontend/js/negotiation.js'});
        await page.evaluate(() => {
            renderNegotiation({active:true, round:1, max_rounds:3, satisfaction:60,
                proposal:{title:'Family function',description:'Agree on a budget',ask:30000},history:[]});
            addBubble('<img src=x onerror="window.injected=true">', 'you');
        });
        assert.equal(await page.locator('#negoAsk').innerText(), 'Rs 30,000');
        assert.equal(await page.locator('#negoChat img').count(), 0);
        assert.equal(await page.evaluate(() => window.injected), undefined);
        console.log('Family offers: desktop/mobile layouts, choice, waiting, skipped, married, locked and affordability states passed.');
    } finally { await browser.close(); }
})().catch(e => {console.error(e); process.exitCode = 1;});
