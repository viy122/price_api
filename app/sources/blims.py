from app.sources._shopify import ShopifyPredictiveSearchSource


class BlimsSource(ShopifyPredictiveSearchSource):
    base_url = "https://blimsfurniture.com.ph"
    seller = "BLIMS Fine Furniture"
    department = "furniture"
