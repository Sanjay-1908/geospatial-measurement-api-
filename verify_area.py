
import geopandas as gpd
from shapely.geometry import Polygon

polygon = Polygon([
    (77.0, 11.0),
    (77.1, 11.0),
    (77.1, 11.1),
    (77.0, 11.1),
    (77.0, 11.0)
])

gdf = gpd.GeoDataFrame(
    {"name": ["Sample Area"]},
    geometry=[polygon],
    crs="EPSG:4326"
)

projected = gdf.to_crs("EPSG:32643")

area_m2 = projected.geometry.area.iloc[0]

print("Area in square metres:", area_m2)
print("Area in square kilometres:", area_m2 / 1_000_000)
print("Area in hectares:", area_m2 / 10_000)
