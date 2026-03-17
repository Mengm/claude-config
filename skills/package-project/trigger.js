/**
 * Trigger Project Package (Default PC Build) on jn-workflow
 *
 * Usage: node trigger-project-package.js <engine_branch> [--headed] [--dry-run]
 *
 * Example:
 *   node trigger-project-package.js UnityBuild_feature/my-branch
 *   node trigger-project-package.js UnityBuild_feature/my-branch --headed --dry-run
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const AUTH_STATE_PATH = path.join(require('os').homedir(), '.claude', 'playwright', 'jnworkflow-auth.json');
const PACKAGE_URL = 'https://jn-workflow.bytedance.net/alfred/projects/t3/jobs/t3/abp/online/development/StandaloneWindows64/-/?page=0&size=10';

function parseArgs() {
    const args = process.argv.slice(2);
    const result = {
        engineBranch: '',
        headed: false,
        dryRun: false
    };

    for (const arg of args) {
        if (arg === '--headed') result.headed = true;
        else if (arg === '--dry-run') result.dryRun = true;
        else if (!result.engineBranch) result.engineBranch = arg;
    }

    if (!result.engineBranch) {
        console.error('Usage: node trigger-project-package.js <engine_branch> [--headed] [--dry-run]');
        process.exit(1);
    }

    return result;
}

async function triggerPackage(opts) {
    if (!fs.existsSync(AUTH_STATE_PATH)) {
        console.error('Auth state not found. Run jnworkflow-login.js first.');
        process.exit(1);
    }

    console.log(`Triggering project package:`);
    console.log(`  Engine Branch: ${opts.engineBranch}`);
    console.log('');

    const browser = await chromium.launch({ headless: !opts.headed });
    const context = await browser.newContext({ storageState: AUTH_STATE_PATH });
    const page = await context.newPage();

    // Navigate to package page
    await page.goto(PACKAGE_URL, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(2000);

    // Check if we're on login page
    const title = await page.title();
    if (title === 'JnWorkflowAuth') {
        console.error('Auth state expired. Re-run jnworkflow-login.js to refresh cookies.');
        await browser.close();
        process.exit(1);
    }

    // Click "默认PC包" button
    await page.click('button.ant-btn-default:has-text("默认PC包")');
    await page.waitForSelector('.ant-modal', { timeout: 5000 });
    await page.waitForTimeout(2000);

    // Set engine branch - it's an ant-select with id "buildInfo-engineBranchName"
    // Click the select to open dropdown
    const engineBranchSelect = page.locator('#buildInfo-engineBranchName').locator('..');
    // Find the ant-select wrapper
    const selectWrapper = page.locator('.ant-select:has(#buildInfo-engineBranchName)');
    await selectWrapper.click();
    await page.waitForTimeout(500);

    // Type to search in the dropdown
    await page.locator('#buildInfo-engineBranchName').fill(opts.engineBranch);
    await page.waitForTimeout(1500); // Wait for search results

    // Select the matching option
    const option = page.locator(`.ant-select-dropdown .ant-select-item-option[title*="${opts.engineBranch}"]`).first();
    const optionExists = await option.count();

    if (optionExists === 0) {
        // Try clicking any option that contains the text
        const anyOption = page.locator(`.ant-select-dropdown .ant-select-item-option`).filter({ hasText: opts.engineBranch }).first();
        const anyOptionExists = await anyOption.count();
        if (anyOptionExists > 0) {
            await anyOption.click();
        } else {
            console.error(`Engine branch "${opts.engineBranch}" not found in dropdown.`);
            console.log('Available options:');
            const allOptions = page.locator('.ant-select-dropdown .ant-select-item-option');
            const count = await allOptions.count();
            for (let i = 0; i < Math.min(count, 10); i++) {
                console.log(`  - ${await allOptions.nth(i).textContent()}`);
            }
            await page.screenshot({ path: path.join(__dirname, '..', 'playwright', 'package-branch-error.png'), fullPage: true });
            await browser.close();
            process.exit(1);
        }
    } else {
        await option.click();
    }

    await page.waitForTimeout(1000);

    if (opts.dryRun) {
        console.log('[DRY RUN] Would click "确 定" to submit. Taking screenshot instead.');
        await page.screenshot({ path: path.join(__dirname, '..', 'playwright', 'package-preview.png'), fullPage: true });
        console.log('Screenshot saved: package-preview.png');
        await browser.close();
        return;
    }

    // Click "确 定" to submit
    await page.click('.ant-modal .ant-btn-primary:has-text("确 定")');
    await page.waitForTimeout(3000);

    // Check if modal closed (success)
    const modalVisible = await page.locator('.ant-modal').isVisible().catch(() => false);
    if (modalVisible) {
        console.error('Modal still visible - package may have failed to trigger.');
        await page.screenshot({ path: path.join(__dirname, '..', 'playwright', 'package-error.png'), fullPage: true });
    } else {
        console.log('Package build triggered successfully!');
    }

    // Get the latest build URL
    await page.waitForTimeout(2000);
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);

    const firstBuildLink = await page.locator('a:has-text("详情")').first().getAttribute('href');
    if (firstBuildLink) {
        const buildUrl = firstBuildLink.startsWith('http') ? firstBuildLink : `https://jn-workflow.bytedance.net${firstBuildLink}`;
        console.log(`\nPackage URL: ${buildUrl}`);
    }

    await browser.close();
}

const opts = parseArgs();
triggerPackage(opts).catch(err => {
    console.error('Error:', err.message);
    process.exit(1);
});
