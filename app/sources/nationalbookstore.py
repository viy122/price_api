from app.sources._shopify import ShopifyPredictiveSearchSource


class NationalBookStoreSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.nationalbookstore.com"
    seller = "National Book Store"
    department = "office"
