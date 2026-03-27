# ArucoCalib

Pixel-to-world coordinate conversion system based on ArUco markers.

## Features

- ArUco marker detection (supports multiple dictionary types)
- Homography-based coordinate transformation (RANSAC)
- Uses all detected calibration markers (`>= 4`)
- YAML-based configuration for flexible world-coordinate setup
- PyQt graphical user interface
- Supports image, live camera, and recorded video (`mp4`) inputs
- Click on the image to get pixel and world coordinates
- Real-time grid and axis overlay

## Create Python Environment

Use `conda` to create an isolated environment:

```bash
conda create -n aruco-calib python=3.10 -y
```

Activate the environment:

```bash
conda activate aruco-calib
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

The system is configured by `config.yaml`. You can customize:

- ArUco dictionary type
- Marker size
- World coordinate definitions (any number of calibration markers)
- Vehicle marker ID (`vehicle_id`)
- Minimum required marker count

Example:

```yaml
aruco:
  dict_type: "DICT_4X4_50"
  marker_size: 0.05

world_coordinates:
  0: [0.0, 0.0]
  1: [0.0, -300.0]
  2: [225.0, -225.0]
  3: [300.0, 0.0]
  # Add more calibration markers if needed

vehicle_id: 0

min_marker_count: 4
```

Vehicle heading (`yaw`) is computed from ArUco corner direction `1 -> 2` for `vehicle_id`, then normalized to `(-180, 180]`.

## Run

```bash
python main.py
```

## Deployment Options

### 1) Quick Start (Desktop Validation)

Use this mode to quickly validate detection, calibration, and coordinate mapping.

1. Print `doc/fast_test.docx`.
2. The template places IDs `1~4` as a square and ID `0` in the center.
3. Keep the printed sheet flat, then test with camera or image input.
4. Use this `config.yaml` mapping:

```yaml
world_coordinates:
  1: [0.0, 0.0]
  2: [100.0, 0.0]
  3: [100.0, 100.0]
  4: [0.0, 100.0]

vehicle_id: 0
```

Notes:
- Each key in `world_coordinates` is a marker ID, and each value is its world position.
- `vehicle_id` is the marker attached to the vehicle. In quick tests, ID `0` can be used as a vehicle proxy.

### 2) Real Deployment (Field Setup)

Use this mode for real-world installation and operation.

1. Print all markers from `doc/ArUco.docx` (IDs `0~19`).
2. Cut each marker by boundary and mount it on a `15 cm x 15 cm` board.
3. Place markers across the area to cover the workspace (avoid near-collinear layouts).
4. In `config.yaml`, define a world coordinate for each deployed marker:

```yaml
world_coordinates:
  1: [x1, y1]
  2: [x2, y2]
  5: [x5, y5]
  9: [x9, y9]
  # ...
```

5. Attach one marker to the vehicle and set:

```yaml
vehicle_id: 0
```

Recommendations:
- Use at least 4 calibration markers with good spatial spread.
- Keep coordinate units consistent (for example, mm).
- Fix camera pose after setup to avoid frequent recalibration.

## Field Deployment

Three common deployment options are listed below. Choose based on your venue constraints and required accuracy.

### Option 1: Ceiling Mount (for teams with sufficient ceiling height)

- Mount the camera on the ceiling with a top-down view of the workspace
- Suitable when ceiling height is sufficient and occlusion is limited
- Recommended field of view (FOV): `60` or `90`
- Pixel recommendation: `1K` is acceptable; use `2K` if higher accuracy is required

### Option 2: Side Mount, Long Distance

- Mount the camera at the side of the venue, relatively far from the target area
- Advantage: simple installation with lower modification cost
- Disadvantage: larger error at far distances
- Recommended field of view (FOV): `60`
- Pixel recommendation: use at least a `2K` camera

### Option 3: Side Mount, Short Distance (with servo gimbal)

- Mount the camera at a closer side position
- Requires a servo gimbal to cover the target area
- Accuracy is significantly better than Option 2
- Recommended field of view (FOV): `45`
- Pixel recommendation: `1K` is acceptable; use `2K` if higher accuracy is required

### Deployment Note

- When using a `2K` camera, ensure the connection uses `USB 3.0` to avoid frame-rate drops or frame loss caused by bandwidth limits.

## Project Structure

- `aruco_core/`: core localization package (ArUco detection, transform, config)
- `aruco_app/`: application layer (PyQt UI)
- `main.py`: single external entry point (forwards to `aruco_app.ui_main.main`)

Import example:

```python
from aruco_core import ArUcoDetector, CoordinateTransformer, get_config
```

## Operation Guide

1. Launch the app and choose input source (image / camera / video).
2. In image mode, click **Load Image** and select a file.
3. In camera mode, click **Start Detection**; optionally record raw frames as `mp4`.
4. In video mode, click **Select Video**, then **Start Detection**.
5. Calibration is updated automatically when enough markers are visible (`>= 4`).
6. Click any image point to inspect pixel and world coordinates.
7. Adjust grid size to change overlay density.

When detection is running in camera/video mode, raw frames are saved under `runs/`, and `images.json` records `img_file_name` and `time`.

Example output structure:

```text
runs/<script_start_ts>/
  img/
    img00000_<time_ms>.jpg
    ...
  images.json
  videos/
    record_<record_start_ts>.mp4
```

## Technical Highlights

- Dynamic calibration point support (not limited to exactly 4 points)
- RANSAC robustness against outliers
- Flexible YAML configuration
- Real-time world-grid and axis visualization

## Changelog

See `CHANGELOG.md` for recent updates.

## License

This project is licensed under the MIT License. See `LICENSE`.

## Contributing

Please read `CONTRIBUTING.md` before submitting pull requests.

## Publish to GitHub

If you have `gh` installed and authenticated, you can publish quickly:

```bash
git init
git add .
git commit -m "Initial open-source release"
gh repo create ArucoCalib --public --source . --remote origin --push
```

Or use classic git remote flow:

```bash
git init
git add .
git commit -m "Initial open-source release"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```
