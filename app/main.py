from __future__ import annotations

import io
import json
import os
import tempfile
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

import geopandas as gpd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pyproj import CRS
from shapely.geometry import (
    GeometryCollection, LineString, MultiLineString, MultiPoint,
    MultiPolygon, Point, Polygon, mapping, shape,
)
from shapely.ops import transform as transform_geometry
from pyproj import Transformer

app = FastAPI(
    title="Geospatial File Measurement API",
    description="Upload KML or zipped Shapefile data and retrieve feature measurements.",
    version="1.0.0",
)

# In-memory storage is intentionally used for this assignment-sized service.
# Data disappears when the server restarts; see README for production improvements.
FILES: dict[str, dict[str, Any]] = {}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
SUPPORTED_MEASUREMENTS = {"Polygon", "MultiPolygon", "LineString", "MultiLineString"}


def _safe_json_value(value: Any) -> Any:
    """Convert common pandas/numpy values into JSON-friendly Python values."""
    if value is None:
        return None
    try:
        # NaN is not valid JSON.
        if value != value:
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _kml_geometry(element: ET.Element):
    """Read common KML geometry elements into Shapely geometries."""
    tag = element.tag.split("}")[-1]
    if tag == "Point":
        coords_el = element.find(".//{*}coordinates")
        if coords_el is None or not coords_el.text:
            return None
        parts = coords_el.text.strip().split()[0].split(",")
        return Point(float(parts[0]), float(parts[1]))

    if tag == "LineString":
        coords_el = element.find("./{*}coordinates")
        if coords_el is None or not coords_el.text:
            return None
        coords = []
        for item in coords_el.text.strip().split():
            p = item.split(",")
            coords.append((float(p[0]), float(p[1])))
        return LineString(coords) if len(coords) >= 2 else None

    if tag == "Polygon":
        outer_el = element.find("./{*}outerBoundaryIs/{*}LinearRing/{*}coordinates")
        if outer_el is None or not outer_el.text:
            return None

        def parse_ring(text: str):
            pts = []
            for item in text.strip().split():
                p = item.split(",")
                pts.append((float(p[0]), float(p[1])))
            return pts

        shell = parse_ring(outer_el.text)
        holes = []
        for inner in element.findall("./{*}innerBoundaryIs/{*}LinearRing/{*}coordinates"):
            if inner.text:
                holes.append(parse_ring(inner.text))
        return Polygon(shell, holes)

    if tag == "MultiGeometry":
        children = []
        for child in list(element):
            geom = _kml_geometry(child)
            if geom is not None:
                children.append(geom)
        if not children:
            return None
        types = {g.geom_type for g in children}
        try:
            if types == {"Point"}:
                return MultiPoint(children)
            if types == {"LineString"}:
                return MultiLineString(children)
            if types == {"Polygon"}:
                return MultiPolygon(children)
        except Exception:
            pass
        return GeometryCollection(children)

    return None


def _read_kml(content: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid KML/XML file: {exc}") from exc

    features = []
    placemarks = root.findall(".//{*}Placemark")
    for index, placemark in enumerate(placemarks):
        name_el = placemark.find("./{*}name")
        description_el = placemark.find("./{*}description")
        props: dict[str, Any] = {}
        if name_el is not None and name_el.text:
            props["name"] = name_el.text
        if description_el is not None and description_el.text:
            props["description"] = description_el.text

        for data in placemark.findall(".//{*}Data"):
            key = data.attrib.get("name")
            value_el = data.find("./{*}value")
            if key:
                props[key] = value_el.text if value_el is not None else None
        for simple in placemark.findall(".//{*}SimpleData"):
            if simple.attrib.get("name"):
                props[simple.attrib["name"]] = simple.text

        geometry = None
        for child in list(placemark):
            if child.tag.split("}")[-1] in {
                "Point", "LineString", "Polygon", "MultiGeometry"
            }:
                geometry = _kml_geometry(child)
                if geometry is not None:
                    break
        if geometry is None:
            # Keep unsupported/missing geometry as a feature instead of crashing.
            features.append({
                "feature_id": index, "geometry_type": "Unknown",
                "geometry": None, "properties": props, "measurement": None,
                "measurement_status": "UNSUPPORTED_GEOMETRY",
            })
        else:
            features.append({
                "feature_id": index, "geometry_type": geometry.geom_type,
                "geometry": geometry, "properties": props,
                "measurement": None, "measurement_status": "PENDING",
            })
    return features


def _read_shapefile_zip(content: bytes) -> tuple[list[dict[str, Any]], str | None]:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            infos = zf.infolist()
            if not infos:
                raise ValueError("The ZIP archive is empty.")
            total_uncompressed = sum(info.file_size for info in infos)
            if total_uncompressed > 100 * 1024 * 1024:
                raise ValueError("ZIP expands beyond the 100 MB processing limit.")
            for info in infos:
                path = PurePosixPath(info.filename)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("ZIP contains an unsafe file path.")
            shp_names = [i.filename for i in infos if i.filename.lower().endswith(".shp")]
            if not shp_names:
                raise ValueError("ZIP must contain a .shp file.")
            # Use the first .shp file. Extract only after checking every member path.
            with tempfile.TemporaryDirectory() as tmp:
                zf.extractall(tmp)
                shp_path = os.path.join(tmp, *PurePosixPath(shp_names[0]).parts)
                if not os.path.isfile(shp_path):
                    raise ValueError("Could not locate the Shapefile after extraction.")
                gdf = gpd.read_file(shp_path)
                source_crs = str(gdf.crs) if gdf.crs else None
                rows = []
                for index, row in gdf.iterrows():
                    geom = row.geometry
                    props = {str(k): _safe_json_value(v) for k, v in row.drop(labels=["geometry"]).to_dict().items()}
                    rows.append({
                        "feature_id": int(index) if isinstance(index, (int,)) else len(rows),
                        "geometry_type": geom.geom_type if geom is not None else "Unknown",
                        "geometry": geom,
                        "properties": props,
                        "measurement": None,
                        "measurement_status": "PENDING" if geom is not None else "UNSUPPORTED_GEOMETRY",
                    })
                return rows, source_crs
    except zipfile.BadZipFile as exc:
        raise ValueError("Uploaded .zip file is not a valid ZIP archive.") from exc
    except (OSError, Exception) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError(f"Could not read Shapefile ZIP: {exc}") from exc


def _geometry_to_json(geom):
    return mapping(geom) if geom is not None else None


def _calculate_measurements(features: list[dict[str, Any]], source_crs_text: str | None):
    if not source_crs_text:
        # Feature information is still returned, but no measurement is guessed.
        for feature in features:
            if feature["geometry"] is not None:
                feature["measurement_status"] = "MISSING_CRS"
        return None

    try:
        source_crs = CRS.from_user_input(source_crs_text)
    except Exception:
        for feature in features:
            if feature["geometry"] is not None:
                feature["measurement_status"] = "INVALID_CRS"
        return None

    # Reproject all measurements into a suitable local UTM CRS, using the
    # combined bounds transformed to WGS84 where possible.
    geometries = [f["geometry"] for f in features if f.get("geometry") is not None]
    target_crs = None
    if geometries:
        try:
            gdf = gpd.GeoDataFrame(geometry=geometries, crs=source_crs)
            if source_crs.is_geographic:
                target_crs = gdf.estimate_utm_crs()
            else:
                # Estimate UTM from the geometry's WGS84 location to ensure metres.
                target_crs = gdf.to_crs("EPSG:4326").estimate_utm_crs()
        except Exception:
            target_crs = None

    if target_crs is None:
        for feature in features:
            if feature["geometry"] is not None:
                feature["measurement_status"] = "CRS_TRANSFORMATION_UNAVAILABLE"
        return None

    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)
    for feature in features:
        geom = feature.get("geometry")
        if geom is None:
            feature["measurement_status"] = "UNSUPPORTED_GEOMETRY"
            continue
        try:
            projected = transform_geometry(transformer.transform, geom)
            kind = geom.geom_type
            if kind in {"Polygon", "MultiPolygon"}:
                feature["measurement"] = {
                    "area": float(projected.area),
                    "area_unit": "m²",
                }
                feature["measurement_status"] = "COMPLETED"
            elif kind in {"LineString", "MultiLineString"}:
                feature["measurement"] = {
                    "length": float(projected.length),
                    "length_unit": "m",
                }
                feature["measurement_status"] = "COMPLETED"
            elif kind in {"Point", "MultiPoint"}:
                feature["measurement"] = None
                feature["measurement_status"] = "NOT_REQUIRED"
            else:
                feature["measurement"] = None
                feature["measurement_status"] = "UNSUPPORTED_GEOMETRY"
        except Exception as exc:
            feature["measurement"] = None
            feature["measurement_status"] = "MEASUREMENT_FAILED"
            feature["measurement_error"] = str(exc)

    return str(target_crs)


def _feature_response(feature: dict[str, Any]) -> dict[str, Any]:
    return {
        "feature_id": feature["feature_id"],
        "geometry_type": feature["geometry_type"],
        "geometry": _geometry_to_json(feature.get("geometry")),
        "crs": feature.get("crs"),
        "properties": feature["properties"],
        "measurement": feature.get("measurement"),
        "measurement_status": feature.get("measurement_status"),
        **({"measurement_error": feature["measurement_error"]} if feature.get("measurement_error") else {}),
    }


@app.get("/")
def root():
    return {"message": "Geospatial File Measurement API", "docs": "/docs"}


@app.post("/api/files/", status_code=201)
async def upload_file(file: UploadFile = File(...)):
    filename = file.filename or "uploaded_file"
    lower_name = filename.lower()
    if not (lower_name.endswith(".kml") or lower_name.endswith(".zip")):
        raise HTTPException(status_code=400, detail="Only .kml and .zip files are supported.")

    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload exceeds the 25 MB limit.")

    try:
        if lower_name.endswith(".kml"):
            features = _read_kml(content)
            source_crs = "EPSG:4326"
        else:
            features, source_crs = _read_shapefile_zip(content)
        if not features:
            raise ValueError("No features were found in the uploaded file.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Could not process file: {exc}") from exc

    measurement_crs = _calculate_measurements(features, source_crs)
    for feature in features:
        feature["crs"] = source_crs

    file_id = uuid.uuid4().hex[:12]
    FILES[file_id] = {
        "id": file_id,
        "filename": os.path.basename(filename),
        "feature_count": len(features),
        "crs": source_crs,
        "measurement_crs": measurement_crs,
        "status": "COMPLETED",
        "features": features,
    }
    return {
        "id": file_id,
        "filename": os.path.basename(filename),
        "feature_count": len(features),
        "crs": source_crs,
        "measurement_crs": measurement_crs,
        "status": "COMPLETED",
        "message": "File uploaded and processed successfully.",
    }


@app.get("/api/files/{file_id}/")
def get_file_info(file_id: str):
    stored = FILES.get(file_id)
    if not stored:
        raise HTTPException(status_code=404, detail="File ID not found. Upload the file again if the server restarted.")
    return {key: stored[key] for key in (
        "id", "filename", "feature_count", "crs", "measurement_crs", "status"
    )}


@app.get("/api/files/{file_id}/measurements/")
def get_measurements(file_id: str):
    stored = FILES.get(file_id)
    if not stored:
        raise HTTPException(status_code=404, detail="File ID not found. Upload the file again if the server restarted.")
    return {
        "id": stored["id"],
        "filename": stored["filename"],
        "source_crs": stored["crs"],
        "measurement_crs": stored["measurement_crs"],
        "feature_count": stored["feature_count"],
        "features": [_feature_response(feature) for feature in stored["features"]],
    }


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc):
    # Keep unexpected errors from leaking a traceback in the API response.
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred."})
