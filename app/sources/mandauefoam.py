from app.sources._shopify import ShopifyPredictiveSearchSource


class MandaueFoamSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.mandauefoam.ph"
    seller = "Mandaue Foam"
    department = "furniture"
