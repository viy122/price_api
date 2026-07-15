from app.sources._shopify import ShopifyPredictiveSearchSource


class ChrisSportsSource(ShopifyPredictiveSearchSource):
    base_url = "https://chrissports.com"
    seller = "Chris Sports"
    department = "sports"
