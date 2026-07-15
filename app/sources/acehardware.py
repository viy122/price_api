from app.sources._shopify import ShopifyPredictiveSearchSource


class AceHardwareSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.acehardware.ph"
    seller = "Ace Hardware PH"
    department = "hardware"
