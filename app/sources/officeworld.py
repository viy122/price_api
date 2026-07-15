from app.sources._shopify import ShopifyPredictiveSearchSource


class OfficeWorldSource(ShopifyPredictiveSearchSource):
    base_url = "https://officeworld.ph"
    seller = "Office World by BLIMS"
    department = "furniture"
