from app.sources._shopify import ShopifyPredictiveSearchSource


class DynaQuestPCSource(ShopifyPredictiveSearchSource):
    base_url = "https://dynaquestpc.com"
    seller = "DynaQuest PC"
    department = "it"
