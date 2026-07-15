from app.sources._shopify import ShopifyPredictiveSearchSource


class StandardWholesaleSource(ShopifyPredictiveSearchSource):
    base_url = "https://standardwholesale.ph"
    seller = "Standard Wholesale"
    department = "janitorial"
