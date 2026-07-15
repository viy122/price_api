from app.sources._shopify import ShopifyPredictiveSearchSource


class OctagonSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.octagon.com.ph"
    seller = "Octagon"
    department = "it"
