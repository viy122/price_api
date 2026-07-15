from app.sources._shopify import ShopifyPredictiveSearchSource


class TobysSportsSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.tobys.com"
    seller = "Toby's Sports"
    department = "sports"
