# demo-shop

A standalone static fake product-listing site, hosted on GitHub Pages, used to demo Argus's self-healing collector.

It contains **two versions of the same page** for the fake smartphone "Argus Phone X1":

- `index.html` — the "before" version. Plain selectors:
  - title: `<h1 class="product-title">`
  - price: `<span class="product-price">`
  - stock: `<span class="stock-status">`
- `index-redesigned.html` — the "after" version. Same product and visible data, but the underlying DOM is restructured to simulate a real site redesign:
  - title: `<h1 class="product-title">` (unchanged)
  - price: `<div class="pricing-value">` nested inside `<div class="price-container">` (was `<span class="product-price">`)
  - stock: `<p data-stock="true">` (was `<span class="stock-status">`)

## Demo procedure

During the live demo (rehearsal or judging), the redesign is simulated by swapping the files:

1. Deploy `index.html` as the live page and point the Argus collector at it. The collector picks up the price and stock via `.product-price` and `.stock-status`.
2. At the demo moment, rename `index-redesigned.html` to `index.html` (replacing the original) and redeploy. Visually the page looks nearly identical, but the original selectors now match nothing.
3. The collector's scrape returns no price/stock, the run is detected as stale/failed, and Argus's heal flow kicks in to rediscover the selectors and recover.

To swap locally:

```bash
# on the deployed copy
mv index.html index-before.html
mv index-redesigned.html index.html
```
