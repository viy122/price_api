from app.sources._woocommerce import WooCommerceSource


class CostULessSource(WooCommerceSource):
    base_url = "https://www.costuless.com.ph"
    seller = "Cost U Less"
    department = "furniture"
