from app.sources._woocommerce import WooCommerceSource


class FurnitureManilaSource(WooCommerceSource):
    base_url = "https://www.furnituremanila.com.ph"
    seller = "Furniture Manila"
    department = "furniture"
