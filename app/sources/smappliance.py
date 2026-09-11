from app.sources._shopify import ShopifyPredictiveSearchSource


class SMApplianceSource(ShopifyPredictiveSearchSource):
    base_url = "https://www.smappliance.com"
    seller = "SM Appliance Center"
    department = "appliances"
    fetch_warranty = True
