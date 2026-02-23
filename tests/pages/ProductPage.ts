import { Page, Locator } from '@playwright/test';

export class ProductPage {
    readonly page: Page;
    readonly addToCartBtn: Locator;

    constructor(page: Page) {
        this.page = page;
        this.addToCartBtn = page.getByRole('button', { name: /Add to Cart/i });
    }

    async addToCart() {
        await this.addToCartBtn.click();
    }
}
