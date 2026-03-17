/**
 * Trigger Engine Build on jn-workflow
 *
 * Usage: node trigger-engine-build.js <branch_name> [commit_id] [--no-dev] [--full-build] [--skip-smoketest] [--headed]
 *
 * Example:
 *   node trigger-engine-build.js feature/my-branch
 *   node trigger-engine-build.js feature/my-branch abc123 --no-dev --headed
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const AUTH_STATE_PATH = path.join(require('os').homedir(), '.claude', 'playwright', 'jnworkflow-auth.json');
const BUILD_URL = 'http://jn-workflow.bytedance.net/alfred/projects/jne/jobs/jne/unity_build/windows_2022/-/?page=0&size=10';

function parseArgs() {
    const args = process.argv.slice(2);
    const result = {
        branchName: '',
        commitId: '',
        noDev: false,
        fullBuild: false,
        skipSmoketest: false,
        headed: false,
        dryRun: false
    };

    for (const arg of args) {
        if (arg === '--no-dev') result.noDev = true;
        else if (arg === '--full-build') result.fullBuild = true;
        else if (arg === '--skip-smoketest') result.skipSmoketest = true;
        else if (arg === '--headed') result.headed = true;
        else if (arg === '--dry-run') result.dryRun = true;
        else if (!result.branchName) result.branchName = arg;
        else if (!result.commitId) result.commitId = arg;
    }

    if (!result.branchName) {
        console.error('Usage: node trigger-engine-build.js <branch_name> [commit_id] [--no-dev] [--full-build] [--skip-smoketest] [--headed] [--dry-run]');
        process.exit(1);
    }

    return result;
}

async function triggerBuild(opts) {
    if (!fs.existsSync(AUTH_STATE_PATH)) {
        console.error('Auth state not found. Run jnworkflow-login.js first.');
        process.exit(1);
    }

    console.log(`Triggering engine build:`);
    console.log(`  Branch: ${opts.branchName}`);
    console.log(`  Commit: ${opts.commitId || '(HEAD)'}`);
    console.log(`  NO_DEV: ${opts.noDev}`);
    console.log(`  FULL_BUILD: ${opts.fullBuild}`);
    console.log(`  SKIP_SMOKETEST: ${opts.skipSmoketest}`);
    console.log('');

    const browser = await chromium.launch({ headless: !opts.headed });
    const context = await browser.newContext({ storageState: AUTH_STATE_PATH });
    const page = await context.newPage();

    // Navigate to build page
    await page.goto(BUILD_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Check if we're on login page (auth expired)
    const title = await page.title();
    if (title === 'JnWorkflowAuth') {
        console.error('Auth state expired. Re-run jnworkflow-login.js to refresh cookies.');
        await browser.close();
        process.exit(1);
    }

    // Click "立即构建" button
    await page.click('button.ant-btn-primary:has-text("立即构建")');
    await page.waitForSelector('.ant-modal', { timeout: 5000 });
    await page.waitForTimeout(1000);

    // Fill branch name
    const branchInput = page.locator('#BRANCH_NAME');
    await branchInput.click({ clickCount: 3 }); // select all
    await branchInput.fill(opts.branchName);

    // Fill commit ID if provided
    if (opts.commitId) {
        const commitInput = page.locator('#COMMIT_ID');
        await commitInput.click({ clickCount: 3 });
        await commitInput.fill(opts.commitId);
    }

    // All three build targets should be checked by default.
    // Ensure they are checked:
    const targets = ['WINDOWS_EDITOR', 'WINDOWS_STANDALONE_SUPPORT', 'ANDROID_PLAYER'];
    for (const target of targets) {
        const checkbox = page.locator(`.ant-checkbox-input[value="${target}"]`);
        const isChecked = await checkbox.isChecked();
        if (!isChecked) {
            await checkbox.check();
        }
    }

    // Handle config checkboxes
    const configMap = {
        'NO_DEV': opts.noDev,
        'FULL_BUILD': opts.fullBuild,
        'SKIP_SMOKETEST': opts.skipSmoketest
    };

    for (const [name, shouldCheck] of Object.entries(configMap)) {
        const checkbox = page.locator(`.ant-checkbox-input[value="${name}"]`);
        const isChecked = await checkbox.isChecked();
        if (shouldCheck && !isChecked) {
            await checkbox.check();
        } else if (!shouldCheck && isChecked) {
            await checkbox.uncheck();
        }
    }

    if (opts.dryRun) {
        console.log('[DRY RUN] Would click "确 定" to submit build. Taking screenshot instead.');
        await page.screenshot({ path: path.join(__dirname, '..', 'playwright', 'engine-build-preview.png'), fullPage: true });
        console.log('Screenshot saved: engine-build-preview.png');
        await browser.close();
        return;
    }

    // Click "确 定" to submit
    await page.click('.ant-modal .ant-btn-primary:has-text("确 定")');
    await page.waitForTimeout(3000);

    // Check if modal closed (success)
    const modalVisible = await page.locator('.ant-modal').isVisible().catch(() => false);
    if (modalVisible) {
        console.error('Modal still visible - build may have failed to trigger.');
        await page.screenshot({ path: path.join(__dirname, '..', 'playwright', 'engine-build-error.png'), fullPage: true });
    } else {
        console.log('Build triggered successfully!');
    }

    // Get the latest build URL (first item in the list after refresh)
    await page.waitForTimeout(2000);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const firstBuildLink = await page.locator('a:has-text("详情")').first().getAttribute('href');
    if (firstBuildLink) {
        const buildUrl = firstBuildLink.startsWith('http') ? firstBuildLink : `http://jn-workflow.bytedance.net${firstBuildLink}`;
        console.log(`\nBuild URL: ${buildUrl}`);
    }

    await browser.close();
}

const opts = parseArgs();
triggerBuild(opts).catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
