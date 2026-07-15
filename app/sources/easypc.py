from app.sources._shopify import ShopifyPredictiveSearchSource


class EasyPCSource(ShopifyPredictiveSearchSource):
    base_url = "https://easypc.com.ph"
    seller = "EasyPC"
    department = "it"
