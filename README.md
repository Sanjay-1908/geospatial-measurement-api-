# Geospatial File Measurement API

A REST API built with FastAPI to upload, process, and measure geospatial files. The API extracts file metadata and calculates polygon area using an appropriate projected coordinate reference system (CRS).

## Features

- Upload geospatial files in ZIP format containing shapefile components.
- Extract metadata, including feature count and coordinate reference system.
- Calculate polygon area in square metres.
- Retrieve uploaded file metadata using a unique file ID.
- Interactive API documentation through Swagger UI.
- Automated API tests.

## Tech Stack

- **Language:** Python
- **API Framework:** FastAPI
- **Geospatial Processing:** GeoPandas, Shapely, PyProj
- **Server:** Uvicorn
- **Testing:** Pytest

## Project Structure

```text
geospatial-measurement-api/
├── app/
├── sample_data/
├── tests/
├── requirements.txt
├── verify_area.py
├── README.md
└── .gitignore
```

## Installation and Setup

### 1. Clone the repository

```bash
git clone https://github.com/Sanjay-1908/geospatial-measurement-api-.git
cd geospatial-measurement-api-
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Start the API server

```bash
uvicorn app.main:app --reload
```

### 5. Open the API documentation

Visit:

http://127.0.0.1:8000/docs

Use Swagger UI to upload files and test the available endpoints.

## API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/files/` | Upload and process a geospatial ZIP file |
| GET | `/api/files/{file_id}/` | Retrieve uploaded file metadata |
| GET | `/api/files/{file_id}/measurements/` | Retrieve geospatial measurements |

## Sample Input

A ZIP archive containing the required shapefile components, such as `.shp`, `.shx`, `.dbf`, and `.prj`.

## Measurement

The API uses a projected CRS suitable for area calculations and returns polygon area in square metres.

## Running Tests

```bash
pytest
```

## Author

**Sanjay S**

GitHub: https://github.com/Sanjay-1908

---

This project demonstrates REST API development, geospatial data processing, coordinate reference systems, and automated testing.