from app.sources._shopify import ShopifyPredictiveSearchSource


class PCExpressSource(ShopifyPredictiveSearchSource):
    base_url = "https://pcx.com.ph"
    seller = "PC Express"
    department = "it"
