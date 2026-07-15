from app.sources._shopify import ShopifyPredictiveSearchSource


class OurHomeSource(ShopifyPredictiveSearchSource):
    base_url = "https://ourhome.ph"
    seller = "Our Home"
    department = "furniture"
