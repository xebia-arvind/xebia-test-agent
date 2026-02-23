import { test, expect } from '../baseTest';
import { HomePage } from '../pages/HomePage';
import { ProductPage } from '../pages/ProductPage';
import { selfHealingClick } from '../utils/selfHealing';
import chalk from 'chalk';

test('User can add product to cart', async ({ page }, testInfo) => {
    console.log(chalk.hex("#00FFFF")('\n========================================'));
    console.log(chalk.hex("#00FFFF")('TEST: User can add product to cart'));
    console.log(chalk.hex("#00FFFF")('========================================'));

    const home = new HomePage(page);
    const product = new ProductPage(page);

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

    console.log('Step 3: Clicking "Add to Cart" button (with self-healing)...');
    await selfHealingClick(
        page,
        product.addToCartBtn,
        'button:has-text("Add to Cart")',
        testInfo,
        {
            use_of_selector: 'click on Add to Cart button',
            selector_type: 'role',
            intent_key: 'add_to_cart',
        }
    );

    console.log('Step 4: Assertion — verifying cart badge is visible...');
    await expect(page.locator('.badge')).toBeVisible();
    console.log('Cart badge is visible');

    console.log('TEST PASSED: Product added to cart successfully\n');
});
