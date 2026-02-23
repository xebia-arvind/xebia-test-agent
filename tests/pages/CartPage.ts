import { Page, Locator } from '@playwright/test';

export class CartPage {
    readonly page: Page;
    readonly cartIcon: Locator;
    readonly checkoutBtn: Locator;

    constructor(page: Page) {
        this.page = page;
        this.cartIcon = page.getByRole('link').filter({ has: page.locator('.bi-bag') })
        this.checkoutBtn = page.locator('text=Proceed to Checkout');
    }

    async openCart() {
        await this.cartIcon.click();
    }

    async goToCheckout() {
        await this.checkoutBtn.click();
    }
}
