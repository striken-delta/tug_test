# ArUco Coordinate Conversion: Core Principles

This document explains three questions for this project:

- What ArUco markers are, why they are used, and how the system detects them
- What a homography matrix is, and how it maps pixel coordinates to world coordinates
- How to improve system stability in practical engineering scenarios

---

## 1. ArUco Markers

### 1.1 What is an ArUco marker

An ArUco marker is a **2D visual marker with a unique ID**. Each marker is a black-and-white coded square. In image processing, the four corners and center can be detected reliably, and the ID can be decoded.

In this project, the dictionary is configured by `config.yaml` (for example `DICT_4X4_50`), and marker world coordinates are defined in `world_coordinates`.

### 1.2 What it does in this system

ArUco markers provide three key functions:

- **Localization**: detect stable reference points in the image
- **Association**: build pixel-to-world correspondences
- **Calibration**: provide input pairs for homography estimation

Without this step, the system only knows image pixels and cannot output world coordinates.

### 1.3 How markers are detected

Current detection flow (`aruco_core/aruco_detector.py`):

1. Convert input image to grayscale (if needed)
2. Use OpenCV ArUco detector to get `corners` and `ids`
3. Draw marker overlays for visualization
4. Compute marker center from corner averages
5. Keep markers that exist in `world_coordinates`

When the number of valid markers meets `min_marker_count`, calibration can proceed.

### 1.4 Common factors affecting detection quality

- Motion blur or defocus
- Glare, overexposure, or heavy shadow
- Marker too small in image or too oblique
- Partial occlusion causing ID decode failure

Best practices: keep markers clear, mostly coplanar, and avoid extreme camera angles.

---

## 2. Homography and Coordinate Mapping

### 2.1 What is a homography matrix

A homography matrix `H` is a `3x3` matrix that models perspective mapping between two 2D coordinate systems on the **same plane**. For pixel point `p=[u,v,1]^T` and world point `P=[x,y,1]^T`:

`s * P = H * p`

`s` is a homogeneous scale factor.  
If points lie on one plane (this project assumes `z=0`), `H` maps image points to world-plane points.

### 2.2 How this project estimates `H`

In `aruco_core/coordinate_transformer.py`, `calibrate()` does:

1. Collect pixel/world point pairs by marker ID
2. Solve `H` with `cv2.findHomography(..., method=cv2.RANSAC)`
3. Compute `H_inv = inv(H)` for world-to-pixel overlay rendering

RANSAC helps keep estimation robust when some points are noisy.

### 2.3 Pixel-to-world conversion path

Full data path:

1. Detector outputs marker center pixels
2. Calibrator estimates `H` from correspondences
3. User clicks pixel `(u,v)`
4. `pixel_to_world()` applies `cv2.perspectiveTransform` with `H`
5. UI displays world `(x,y)` (currently with fixed `z=0.0`)

Grid/axis overlay uses the reverse path: `(x,y)` projected back to pixels via `H_inv`.

### 2.4 Assumptions and limits

Key assumptions:

- Target points are approximately coplanar
- Camera distortion impact is acceptable (or corrected beforehand)
- Marker layout in world coordinates is known

Typical limits:

- Significant out-of-plane height introduces systematic error
- Strong marker jitter causes unstable `H` and output jitter

---

## 3. Three Ways to Improve Stability

These methods address detection, estimation, and temporal behavior.

### 3.1 Method 1: Detection-layer stabilization

Goal: reduce noisy inputs and false detections.

Practical actions:

- Ensure markers are large enough in image pixels
- Tune exposure/shutter to reduce blur and clipping
- Recalibrate only under reliable marker visibility

Current status:

- Detection parameters can be controlled through `aruco_params` in `config.yaml`
- Calibration is gated by `min_marker_count`

### 3.2 Method 2: Estimation-layer stabilization

Goal: make `H` less sensitive to local errors.

Practical actions:

- Use `RANSAC` (already enabled)
- Keep deterministic ID-based point pairing
- Add geometric quality checks (distribution area, degeneracy, reprojection error)
- Validate invertibility of `H`

Current status:

- Uses `findHomography(..., RANSAC)` and inverse-matrix failure handling
- Can be extended with reprojection-error acceptance thresholds

### 3.3 Method 3: Temporal stabilization

Temporal smoothing/hold strategies can improve continuity when markers are briefly lost in video streams, but strategy choice depends on your application latency and accuracy constraints.

---

## 4. Mapping to Project Modules

- Detection: `aruco_core/aruco_detector.py`
  - `detect_markers()`
  - `get_marker_centers()`
  - `get_required_markers()`
- Coordinate transform: `aruco_core/coordinate_transformer.py`
  - `calibrate()`
  - `pixel_to_world()`
  - `world_to_pixel()`
- Configuration: `aruco_core/config_loader.py`
  - `ARUCO_DICT`, `WORLD_COORDINATES`, `MIN_MARKER_COUNT`, `VEHICLE_ID`
- UI orchestration: `aruco_app/ui_main.py`
  - `detect_and_calibrate()`

---

## 5. Recommended Tuning Order

Tune in this order:

1. Detection quality first (image quality, marker size, detector params)
2. Homography robustness second (RANSAC behavior, geometric checks)
3. Temporal continuity third (optional smoothing/hold strategy)

---

## 6. One-line Summary

The system uses ArUco markers to build pixel-world correspondences, estimates a plane homography for coordinate mapping, and maintains practical stability through detection and estimation robustness.

