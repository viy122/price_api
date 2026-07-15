from app.sources._woocommerce import WooCommerceSource


class PhilMedicalSuppliesSource(WooCommerceSource):
    base_url = "https://philmedicalsupplies.com"
    seller = "Phil Medical Supplies"
    department = "medical"
