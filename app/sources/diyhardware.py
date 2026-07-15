from app.sources._shopify import ShopifyPredictiveSearchSource


class DIYHardwareSource(ShopifyPredictiveSearchSource):
    base_url = "https://diyhardware.ph"
    seller = "DIY Hardware"
    department = "hardware"
