import { test, expect } from '../baseTest';
import { HomePage } from '../pages/HomePage';
import { selfHealingClick } from '../utils/selfHealing';
import chalk from 'chalk';

test('User can open product detail page', async ({ page }, testInfo) => {
    console.log(chalk.hex("#00FFFF")('\n========================================'));
    console.log(chalk.hex("#00FFFF")('TEST: User can open product detail page'));
    console.log(chalk.hex("#00FFFF")('========================================'));

    const home = new HomePage(page);

    console.log('Step 1: Navigating to home page...');
    await home.goto();

    console.log('Step 2: Clicking first "View Details" link (with self-healing)...');
    await selfHealingClick(
        page,
        home.productLinks.first(),
        'a:has-text("View Details")',
        testInfo,
        {
            use_of_selector: 'click on first View Details product link',
            selector_type: 'text',
            intent_key: 'view_details',
        }
    );

    console.log('Step 3: Verifying URL contains /product/...');
    await expect(page).toHaveURL(/product/);

    console.log('TEST PASSED: Product detail page opened\n');
});
