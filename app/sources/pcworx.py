from app.sources._shopify import ShopifyPredictiveSearchSource


class PCWorxSource(ShopifyPredictiveSearchSource):
    base_url = "https://pcworx.ph"
    seller = "PCWorx"
    department = "it"
