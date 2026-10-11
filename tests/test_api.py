from fastapi.testclient import TestClient
from app.main import app, FILES

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_reject_unsupported_extension():
    response = client.post(
        "/api/files/",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 400


def test_unknown_file_id():
    response = client.get("/api/files/not-a-real-id/")
    assert response.status_code == 404


def test_upload_kml_and_measurements():
    FILES.clear()
    kml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <Placemark><name>Small square</name><Polygon><outerBoundaryIs><LinearRing>
        <coordinates>11.0000,76.0000,0 11.0010,76.0000,0 11.0010,76.0010,0 11.0000,76.0010,0 11.0000,76.0000,0</coordinates>
      </LinearRing></outerBoundaryIs></Polygon></Placemark>
      <Placemark><name>Road</name><LineString>
        <coordinates>11.0000,76.0000,0 11.0020,76.0020,0</coordinates>
      </LineString></Placemark>
      <Placemark><name>Building</name><Point><coordinates>11.0005,76.0005,0</coordinates></Point></Placemark>
    </Document></kml>"""
    response = client.post(
        "/api/files/",
        files={"file": ("sample.kml", kml, "application/vnd.google-earth.kml+xml")},
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["feature_count"] == 3
    file_id = data["id"]

    info = client.get(f"/api/files/{file_id}/")
    assert info.status_code == 200
    assert info.json()["crs"] == "EPSG:4326"

    measurements = client.get(f"/api/files/{file_id}/measurements/")
    assert measurements.status_code == 200
    features = measurements.json()["features"]
    assert features[0]["measurement"]["area"] > 0
    assert features[1]["measurement"]["length"] > 0
    assert features[2]["measurement"] is None
    assert features[2]["measurement_status"] == "NOT_REQUIRED"
