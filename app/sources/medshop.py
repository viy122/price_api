from app.sources._shopify import ShopifyPredictiveSearchSource


class MedShopSource(ShopifyPredictiveSearchSource):
    base_url = "https://medshop.com.ph"
    seller = "MedShop"
    department = "medical"
