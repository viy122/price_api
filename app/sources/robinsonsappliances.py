from app.sources._shopify import ShopifyPredictiveSearchSource


class RobinsonsAppliancesSource(ShopifyPredictiveSearchSource):
    base_url = "https://robinsonsappliances.com.ph"
    seller = "Robinsons Appliances"
    department = "appliances"
    fetch_warranty = True
