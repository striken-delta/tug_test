# Contributing

Thanks for your interest in improving ArucoCalib.

## Development setup

1. Create and activate environment:
   - `conda create -n aruco-calib python=3.10 -y`
   - `conda activate aruco-calib`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run application:
   - `python main.py`

## Pull request process

1. Create a feature branch from `main`.
2. Keep changes focused and include documentation updates when behavior changes.
3. Run basic local validation before opening PR:
   - App starts successfully
   - Marker detection flow works on one sample image/video
4. Open a PR with:
   - What changed
   - Why it changed
   - How it was tested

## Code style

- Follow existing Python style and naming conventions.
- Prefer clear, small functions and explicit variable names.
- Keep UI text and docs consistent with actual behavior.
