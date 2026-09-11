from app.sources.villman import VillManSource
from app.sources.complink import ComplinkSource
from app.sources.octagon import OctagonSource
from app.sources.philmedicalsupplies import PhilMedicalSuppliesSource
from app.sources.officewarehouse import OfficeWarehouseSource
from app.sources.medshop import MedShopSource
from app.sources.standardwholesale import StandardWholesaleSource
from app.sources.papercart import PaperCartSource
from app.sources.officeworks import OfficeWorksSource
from app.sources.bultuhan import BultuhanSource
from app.sources.blims import BlimsSource
from app.sources.officeworld import OfficeWorldSource
from app.sources.ourhome import OurHomeSource
from app.sources.furnituremanila import FurnitureManilaSource
from app.sources.costuless import CostULessSource
from app.sources.wilcon import WilconSource
from app.sources.acehardware import AceHardwareSource
from app.sources.diyhardware import DIYHardwareSource
from app.sources.nationalbookstore import NationalBookStoreSource
from app.sources.robinsonsappliances import RobinsonsAppliancesSource
from app.sources.smappliance import SMApplianceSource
from app.sources.pcexpress import PCExpressSource
from app.sources.dynaquest import DynaQuestPCSource
from app.sources.pcworx import PCWorxSource
from app.sources.easypc import EasyPCSource
from app.sources.tobys import TobysSportsSource
from app.sources.sportscentral import SportsCentralSource
from app.sources.chrissports import ChrisSportsSource
from app.sources.rosepharmacy import RosePharmacySource
from app.sources.metro import MetroSource
from app.sources.laptopfactory import LaptopFactorySource
from app.sources.mandauefoam import MandaueFoamSource
from app.sources.discovery import build_dynamic_source
from app import vendor_registry

SOURCES = [
    VillManSource(), ComplinkSource(), OctagonSource(),
    PhilMedicalSuppliesSource(), OfficeWarehouseSource(), MedShopSource(),
    StandardWholesaleSource(), PaperCartSource(), OfficeWorksSource(), BultuhanSource(),
    BlimsSource(), OfficeWorldSource(), OurHomeSource(), FurnitureManilaSource(), CostULessSource(),
    WilconSource(), AceHardwareSource(), DIYHardwareSource(), NationalBookStoreSource(),
    RobinsonsAppliancesSource(), SMApplianceSource(),
    PCExpressSource(), DynaQuestPCSource(), PCWorxSource(), EasyPCSource(),
    TobysSportsSource(), SportsCentralSource(), ChrisSportsSource(),
    RosePharmacySource(), MetroSource(),
    LaptopFactorySource(), MandaueFoamSource(),
]

for _row in vendor_registry.list_approved():
    SOURCES.append(
        build_dynamic_source(_row.id, _row.platform, _row.base_url, _row.seller, _row.department)
    )
