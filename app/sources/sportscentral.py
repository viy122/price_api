from app.sources._shopify import ShopifyPredictiveSearchSource


class SportsCentralSource(ShopifyPredictiveSearchSource):
    base_url = "https://sportscentral.ph"
    seller = "Sports Central"
    department = "sports"
