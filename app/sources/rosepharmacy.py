from app.sources._woocommerce import WooCommerceSource


class RosePharmacySource(WooCommerceSource):
    base_url = "https://rosepharmacy.com"
    seller = "Rose Pharmacy"
    department = "medical"
