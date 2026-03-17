/**
 * jn-workflow SSO Login Helper
 *
 * Opens a headed browser for manual SSO login.
 * Saves auth state (cookies + localStorage) for later headless use.
 *
 * Usage: node jnworkflow-login.js
 */

const { chromium } = require('playwright');
const path = require('path');

const AUTH_STATE_PATH = path.join(require('os').homedir(), '.claude', 'playwright', 'jnworkflow-auth.json');
const TARGET_URL = 'http://jn-workflow.bytedance.net/alfred/projects/jne/jobs/jne/unity_build/windows_2022/-/?page=0&size=10';

async function login() {
    console.log('Launching browser for SSO login...');
    console.log('Please complete the login in the browser window.');
    console.log('The browser will close automatically once login is detected.\n');

    const browser = await chromium.launch({ headless: false });
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto(TARGET_URL, { waitUntil: 'domcontentloaded', timeout: 60000 });

    console.log('Waiting for login to complete...');
    console.log('Click the login button and complete SSO in the browser window.');

    // Poll for login completion - SSO will redirect across domains,
    // so we can't use waitForFunction (it breaks on navigation).
    const deadline = Date.now() + 300000; // 5 min
    while (Date.now() < deadline) {
        try {
            const title = await page.title();
            const url = page.url();
            // Login is complete when:
            // 1. We're back on jn-workflow.bytedance.net
            // 2. The page title is NOT "JnWorkflowAuth" (the login page title)
            if (url.includes('jn-workflow.bytedance.net') && title && title !== 'JnWorkflowAuth') {
                console.log(`Login detected! Page title: "${title}"`);
                break;
            }
        } catch (e) {
            // Page might be navigating, ignore errors
        }
        await new Promise(r => setTimeout(r, 1000));
    }

    if (Date.now() >= deadline) {
        console.error('Login timed out (5 min).');
        await browser.close();
        process.exit(1);
    }

    // Give cookies time to settle
    await page.waitForTimeout(3000);

    // Save auth state
    await context.storageState({ path: AUTH_STATE_PATH });
    console.log(`\nAuth state saved to: ${AUTH_STATE_PATH}`);
    console.log('You can now use the automation scripts without manual login.');

    await browser.close();
}

login().catch(err => {
    console.error('Login failed:', err.message);
    process.exit(1);
});
