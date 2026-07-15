from app.sources._shopify import ShopifyPredictiveSearchSource


class ComplinkSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.complink.com.ph"
    seller = "Complink"
    department = "it"
