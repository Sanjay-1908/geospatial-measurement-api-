# Geospatial File Measurement API

A Python backend API built with FastAPI that accepts KML files and ZIP archives containing Shapefiles, extracts feature information, and calculates polygon area or line length.

## Features

- Upload `.kml` or `.zip` (Shapefile archive) files.
- Return feature index, geometry type, geometry, source CRS, and properties.
- Calculate polygon area in square metres and line length in metres.
- Do not calculate measurements for Point features.
- Reproject geometries into a locally estimated UTM CRS before measurement.
- Handle unsupported geometries and missing/invalid CRS information without intentionally crashing the entire processing flow.
- Interactive API documentation at `/docs`.
- Basic automated tests.

## Requirements

- Python 3.10 or newer recommended.
- `pip`
- For a Shapefile ZIP, include the `.shp`, `.shx`, and `.dbf` files. Include `.prj` whenever available so the coordinate system can be identified.

## Run locally (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

If PowerShell blocks virtual-environment activation, use Command Prompt instead:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs to test the API. Use the file input on `POST /api/files/` to upload `sample_data/sample.kml`.

## API endpoints

### 1. Upload and process a file

`POST /api/files/`

Content type: `multipart/form-data`, field name: `file`.

Accepted extensions: `.kml`, `.zip`.

Example response:

```json
{
  "id": "abc123def456",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32632",
  "status": "COMPLETED",
  "message": "File uploaded and processed successfully."
}
```

IDs and the selected measurement CRS depend on the uploaded file; the above is illustrative.

### 2. Get file information

`GET /api/files/{id}/`

Example response:

```json
{
  "id": "abc123def456",
  "filename": "sample.kml",
  "feature_count": 3,
  "crs": "EPSG:4326",
  "measurement_crs": "EPSG:32632",
  "status": "COMPLETED"
}
```

### 3. Get feature measurements

`GET /api/files/{id}/measurements/`

Example response shape:

```json
{
  "id": "abc123def456",
  "filename": "sample.kml",
  "source_crs": "EPSG:4326",
  "measurement_crs": "a suitable projected CRS",
  "feature_count": 1,
  "features": [
    {
      "feature_id": 0,
      "geometry_type": "Polygon",
      "geometry": {"type": "Polygon", "coordinates": []},
      "crs": "EPSG:4326",
      "properties": {"name": "Sample land plot"},
      "measurement": {"area": 10000.0, "area_unit": "m²"},
      "measurement_status": "COMPLETED"
    }
  ]
}
```

The example area is illustrative. Actual values are calculated from the uploaded geometry.

Measurement status values include `COMPLETED`, `NOT_REQUIRED`, `UNSUPPORTED_GEOMETRY`, `MISSING_CRS`, `INVALID_CRS`, and `MEASUREMENT_FAILED`.

## Architecture and processing flow

1. FastAPI validates the filename and upload size.
2. KML files are parsed from XML; ZIP archives are validated and the Shapefile is read using GeoPandas.
3. Each feature is represented with its geometry, attributes, ID/index, and geometry type.
4. The source CRS is identified. KML is treated as EPSG:4326, as defined by the KML format.
5. A local UTM projected CRS is estimated for the data. Geometries are transformed with PyProj/Shapely before area and length calculations.
6. Polygon/MultiPolygon features receive area in m²; LineString/MultiLineString features receive length in m; Point/MultiPoint features require no measurement.
7. Processed file information and features are held in memory and returned through GET endpoints.

## Design decisions and limitations

- **FastAPI:** lightweight, type-friendly, and provides interactive OpenAPI docs.
- **GeoPandas/Shapely/PyProj:** common Python geospatial tools for reading vector data, geometry operations, and CRS transformations.
- **UTM measurement CRS:** a practical choice for local/regional datasets. A single UTM CRS may not be suitable for very large or multi-zone/global datasets; a production service should choose CRS based on each feature/region or use a suitable geodesic strategy.
- **In-memory storage:** keeps the assignment implementation small. Data is lost when the process restarts and multiple server workers will not share state. Production should use persistent storage and a database.
- **KML parser scope:** supports common Placemark Point, LineString, Polygon, and MultiGeometry structures and basic name/description/ExtendedData attributes. Complex KML styles, NetworkLinks, and some uncommon structures are outside this starter implementation.
- **Shapefile ZIP:** the implementation reads the first `.shp` found in the archive. Archives with multiple Shapefiles should be handled by a future explicit selection feature.
- **Security:** upload size and ZIP path checks are included. A production deployment should also add authentication, rate limits, malware scanning, stronger resource limits, and background processing.

## Tests

```powershell
pytest -q
```

Tests cover the root endpoint, unsupported extension, unknown IDs, and a KML upload with polygon, line, and point features.

## Learning outcomes

This project demonstrates REST API design, multipart file uploads, geospatial vector data processing, geometry types, coordinate reference systems, projection-aware measurement, JSON responses, validation, error handling, and automated testing.

## Future scope

- Persistent database and file/object storage.
- Background processing for large uploads.
- Authentication and per-user file access.
- Support for GeoJSON and additional GIS formats.
- More robust KML parsing and multiple Shapefile selection.
- Per-feature CRS selection for wide-area datasets.
- Docker deployment, CI tests, and monitoring.
- Optional map-based frontend to visualize uploaded features and measurements.
