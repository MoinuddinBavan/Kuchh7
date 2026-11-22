"""Stage 1 sample libraries. No prices or approved manufacturing specifications."""

from __future__ import annotations

from dataclasses import dataclass


FURNITURE = "Furniture"
APPLIANCES = "Appliances, Sinks & Taps"
PROPS = "Decorative Props"
HARDWARE = "Hardware & Accessories"
LIBRARIES = (FURNITURE, APPLIANCES, PROPS, HARDWARE)
APPEARANCE_COLOURS = {
    "Stainless": "#AAB5B8",
    "Graphite": "#43474A",
    "Warm White": "#E8E5DE",
}


def product_colour(type_id: str, appearance: str = "Catalogue") -> str:
    return get_product(type_id).colour if appearance == "Catalogue" else APPEARANCE_COLOURS[appearance]


@dataclass(frozen=True)
class ProductDefinition:
    type_id: str
    library: str
    category: str
    name: str
    width: int
    depth: int
    height: int
    elevation_z: int = 0
    colour: str = "#89949A"
    shape: str = "box"
    treatment: str = "review_required"


PRODUCTS = (
    ProductDefinition("oven_freestanding", APPLIANCES, "Cooking", "Freestanding Oven", 600, 600, 850, colour="#4C555B", shape="oven"),
    ProductDefinition("hob_4_zone", APPLIANCES, "Cooking", "Four-zone Hob", 600, 520, 35, 740, "#30383D", "hob"),
    ProductDefinition("fridge_tall", APPLIANCES, "Cooling", "Tall Refrigerator", 700, 700, 1900, colour="#C4CBCB", shape="fridge"),
    ProductDefinition("sink_single", APPLIANCES, "Water", "Single Bowl Sink", 550, 450, 160, 740, "#A6B0B4", "sink"),
    ProductDefinition("tap_arc", APPLIANCES, "Water", "Arc Kitchen Tap", 90, 180, 300, 740, "#AEB8BB", "tap"),
    ProductDefinition("dishwasher", APPLIANCES, "Cleaning", "Dishwasher", 600, 600, 850, colour="#BFC6C8", shape="appliance"),
    ProductDefinition("plant_pot", PROPS, "Greenery", "Potted Plant", 210, 210, 350, 740, "#53775B", "plant", "visual_only"),
    ProductDefinition("ceramic_vase", PROPS, "Decor", "Ceramic Vase", 150, 150, 280, 740, "#D9D1C5", "vase", "visual_only"),
    ProductDefinition("utensil_jar", PROPS, "Countertop", "Utensil Jar", 160, 160, 260, 740, "#B69A79", "jar", "visual_only"),
    ProductDefinition("pendant_light", PROPS, "Lighting", "Pendant Light", 300, 300, 400, 2150, "#C1B29A", "light", "visual_only"),
    ProductDefinition("cutting_board", PROPS, "Countertop", "Decorative Cutting Board", 320, 200, 25, 740, "#C3A47E", "board", "visual_only"),
    ProductDefinition("potted_green_plant", PROPS, "Greenery", "Potted Green Plant", 240, 240, 380, 740, "#55765A", "potted_green_plant", "visual_only"),
    ProductDefinition("flower_vase", PROPS, "Decor", "Flower Vase", 220, 220, 420, 740, "#C9D0C7", "flower_vase", "visual_only"),
    ProductDefinition("floor_plant", PROPS, "Greenery", "Floor Plant", 420, 420, 1250, 0, "#47694D", "floor_plant", "visual_only"),
    ProductDefinition("decorative_vase", PROPS, "Decor", "Decorative Vase", 190, 190, 450, 740, "#B9AA98", "decorative_vase", "visual_only"),
    ProductDefinition("fruit_bowl", PROPS, "Countertop", "Fruit Bowl", 300, 250, 160, 740, "#D2C3A8", "fruit_bowl", "visual_only"),
    ProductDefinition("utensil_holder", PROPS, "Countertop", "Utensil Holder", 180, 180, 350, 740, "#D2C6B5", "utensil_holder", "visual_only"),
    ProductDefinition("decorative_tray", PROPS, "Countertop", "Decorative Tray", 340, 230, 150, 740, "#A89B8B", "decorative_tray", "visual_only"),
    ProductDefinition("small_sculpture", PROPS, "Shelf Decor", "Small Sculpture", 150, 140, 145, 1655, "#D6CEC2", "small_sculpture", "visual_only"),
    ProductDefinition("hinge_soft_close", HARDWARE, "Hinges", "Concealed Hinge · Sample", 35, 50, 15),
    ProductDefinition("handle_bar", HARDWARE, "Handles", "Bar Handle · Sample", 160, 25, 30),
    ProductDefinition("runner_pair", HARDWARE, "Runners", "Drawer Runner Pair · Sample", 450, 45, 20),
    ProductDefinition("shelf_support", HARDWARE, "Supports", "Shelf Support · Sample", 20, 20, 15),
)

PRODUCTS_BY_ID = {item.type_id: item for item in PRODUCTS}
CURATED_PROP_IDS = frozenset({
    "potted_green_plant", "flower_vase", "floor_plant", "decorative_vase",
    "fruit_bowl", "utensil_holder", "decorative_tray", "small_sculpture",
})


def products_for(library: str) -> tuple[ProductDefinition, ...]:
    return tuple(item for item in PRODUCTS if item.library == library)


def get_product(type_id: str) -> ProductDefinition:
    try:
        return PRODUCTS_BY_ID[type_id]
    except KeyError as error:
        raise ValueError(f"Unknown library product: {type_id}") from error
