import { HomePage } from '../pages/HomePage';
import chalk from 'chalk';
import { test, expect } from "../baseTest";

test('User can see products on home page', async ({ page }) => {
    console.log(chalk.hex("#00FFFF")('\n========================================'));
    console.log(chalk.hex("#00FFFF")('TEST: User can see products on home page'));
    console.log(chalk.hex("#00FFFF")('========================================'));

    const home = new HomePage(page);

    console.log('Step 1: Navigating to home page...');
    await home.goto();

    console.log('Step 2: Verifying 3 product links are visible...');
    await expect(home.productLinks).toHaveCount(3);

    console.log('TEST PASSED: Home page shows 3 products\n');
});
