from app.sources._woocommerce import WooCommerceSource


class LaptopFactorySource(WooCommerceSource):
    base_url = "https://laptopfactory.com.ph"
    seller = "Laptop Factory"
    department = "it"
