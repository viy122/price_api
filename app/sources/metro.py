from app.sources._woocommerce import WooCommerceSource


class MetroSource(WooCommerceSource):
    base_url = "https://shopmetro.ph"
    seller = "Metro"
    department = "janitorial"
