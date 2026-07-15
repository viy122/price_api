from app.sources._shopify import ShopifyPredictiveSearchSource


class PaperCartSource(ShopifyPredictiveSearchSource):
    base_url = "https://papercart.ph"
    seller = "Paper Cart"
    department = "office"
