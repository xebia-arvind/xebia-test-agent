import { Page, Locator } from '@playwright/test';

export class HomePage {
    readonly page: Page;
    readonly productLinks: Locator;

    constructor(page: Page) {
        this.page = page;
        this.productLinks = page.locator('a:has-text("View Details")');
    }

    async goto() {
        await this.page.goto('/');
    }

    async clickFirstProduct() {
        await this.productLinks.first().click();
    }
}
