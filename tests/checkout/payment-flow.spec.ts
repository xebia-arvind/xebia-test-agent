import { test, expect } from '../baseTest';
import { selfHealingClick } from '../utils/selfHealing';
import chalk from 'chalk';

test('User can complete checkout flow', async ({ page }, testInfo) => {
    console.log(chalk.hex("#00FFFF")('\n========================================'));
    console.log(chalk.hex("#00FFFF")('TEST: User can complete checkout flow'));
    console.log(chalk.hex("#00FFFF")('========================================'));

    console.log('Step 1: Navigating to home page & clearing localStorage...');
    await page.goto('/');
    await page.evaluate(() => localStorage.clear());

    console.log('Step 2: Clicking first "View Details" product link (rimary locator intentionally broken)...');
    await selfHealingClick(
        page,
        page.getByRole('link', { name: /View Details/i }).first(),
        //page.locator('#product_view_details'),
        '#product_view_details")',
        testInfo,
        {
            use_of_selector: 'click on first View Details product link',
            selector_type: 'text',
            intent_key: 'view_details',
        }
    );

    console.log('Step 3: Assertion — verifying navigation to product detail page...');
    await expect(page).toHaveURL(/product/);
    console.log('   ✔ URL confirmed: contains /product/');

    console.log('Step 4: Clicking "Add to Cart" (with self-healing)...');
    await selfHealingClick(
        page,
        page.getByRole('button', { name: /Add to Cart/i }),
        "button.old-add-to-cart",
        testInfo,
        {
            use_of_selector: "click on Add to Cart button",
            selector_type: "role",
            intent_key: 'add_to_cart',
        }
    );

    console.log('Step 5: Clicking cart icon (with self-healing)...');
    await selfHealingClick(
        page,
        page.getByTestId('cart-icon'),
        "button.old-cart-icon",
        testInfo,
        {
            use_of_selector: "click on Cart icon",
            selector_type: "test-id",
            intent_key: 'cart',
        }
    );

    console.log('Step 6: Clicking "Proceed to Checkout" (with self-healing)...');
    await selfHealingClick(
        page,
        page.getByRole('link', { name: /Proceed to Checkout/i }),
        "a.old-checkout-link",
        testInfo,
        {
            use_of_selector: "click on Proceed to Checkout link",
            selector_type: "role",
            intent_key: 'checkout',
        }
    );

    console.log('Step 7: Filling shipping details...');
    const shipping = page.getByTestId('shipping-section');
    await shipping.getByPlaceholder('Full Name').fill('Arvind');
    await shipping.getByPlaceholder('Address').fill('Delhi');
    await shipping.getByPlaceholder('City').fill('Delhi');
    await shipping.getByPlaceholder('ZIP Code').fill('110001');
    console.log('   → Full Name: Arvind | Address: Delhi | City: Delhi | ZIP: 110001');

    // ── SHOWCASE: Self-Healing with 3 selector strategies ──────────────────────
    // Each attempt uses a deliberately broken primary locator so the healer
    // kicks in and demonstrates fallback via role → class → id selectors.

    // console.log('📌 Step 8a: [ROLE-BASED] Clicking "Pay Now" — primary locator intentionally broken...');
    // await selfHealingClick(
    //     page,
    //     page.getByRole('button', { name: /PayNow_BROKEN_ROLE/i }),   // ← broken on purpose
    //     'button[role="button"]:has-text("Pay Now")',                   // fallback CSS (role attr)
    //     testInfo.title,
    //     {
    //         use_of_selector: 'click on Pay Now button — role-based selector demo',
    //         selector_type: 'role',
    //     }
    // );

    // Uncomment the blocks below to also demo class-based and id-based healing.
    // Only one click is needed to actually submit the form; the others are for
    // showcase purposes and should be run on a page where the button is still visible.

    /*
    console.log('📌 Step 8b: [CLASS-BASED] Clicking "Pay Now" — primary locator intentionally broken...');
    await selfHealingClick(
        page,
        page.locator('button.pay-now-BROKEN-CLASS'),                   // ← broken on purpose
        'button.pay-now-button',                                       // fallback CSS (real class)
        testInfo.title,
        {
            use_of_selector: 'click on Pay Now button — class-based selector demo',
            selector_type: 'css-class',
        }
    );*/

    console.log('Step 8c: [ID-BASED] Clicking "Pay Now" — primary locator intentionally broken...');
    await selfHealingClick(
        page,
        page.locator('#pay-now-BROKEN-ID'),                            // ← broken on purpose
        '#pay-now-BROKEN-ID',                                                // fallback CSS (real id)
        testInfo,
        {
            use_of_selector: 'click on Pay Now button',
            selector_type: 'css-id',
            intent_key: 'payment',
        }
    );


    console.log('Step 9: Assertion — verifying "Payment Successful" message...');
    await expect(page.getByText(/Payment Successful/i)).toBeVisible();
    console.log('   ✔ "Payment Successful" message is visible');

    console.log('TEST PASSED: Full checkout flow completed successfully\n');

})
