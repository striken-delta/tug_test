"""
Configuration loader module for ArUco coordinate system.
Loads YAML config with fallback search paths.
"""
from pathlib import Path
import yaml
import cv2
import numpy as np


class Config:
    """Configuration class that loads settings from YAML file"""
    
    def __init__(self, config_file='config.yaml'):
        """
        Initialize configuration from YAML file
        
        Args:
            config_file: Path to YAML configuration file (default: 'config.yaml')
        """
        config_path = self._resolve_config_path(config_file)

        # Load YAML configuration
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
        
        # Parse ArUco settings
        aruco_config = config_data.get('aruco', {})
        dict_type_name = aruco_config.get('dict_type', 'DICT_4X4_50')
        
        # Convert string to cv2 constant
        self.ARUCO_DICT = getattr(cv2.aruco, dict_type_name)
        self.MARKER_SIZE = aruco_config.get('marker_size', 0.05)

        # Optional: ArUco detector params overrides
        self.ARUCO_PARAMS = config_data.get("aruco_params", {}) or {}

        # Parse world coordinates
        world_coords = config_data.get('world_coordinates', {})
        self.WORLD_COORDINATES = {}
        for marker_id, coords in world_coords.items():
            # Convert to int key and numpy array
            self.WORLD_COORDINATES[int(marker_id)] = np.array(coords, dtype=np.float32)
        
        # Parse minimum marker count
        self.MIN_MARKER_COUNT = config_data.get('min_marker_count', 4)

        # Optional UI settings
        ui_config = config_data.get("ui", {}) or {}
        self.TRACE_WINDOW_MS = int(ui_config.get("trace_window_ms", 500))

        # Camera settings
        camera_config = config_data.get("camera", {}) or {}
        self.CAMERA_TYPE = str(camera_config.get("type", "opencv")).lower()
        self.OPENCV_DEVICE_INDEX = int(camera_config.get("opencv_device_index", 0))
        self.DAHENG_DEVICE_INDEX = int(camera_config.get("daheng_device_index", 1))
        self.EXPOSURE_TIME_US = float(camera_config.get("exposure_time_us", -1))
        self.GAIN_DB = float(camera_config.get("gain_db", -1))

        # Vehicle marker ID (ArUco marker_id on the car)
        # Prefer `vehicle_id`; keep `car_id` for backward compatibility.
        self.VEHICLE_ID = int(config_data.get("vehicle_id", config_data.get("car_id", 0)))

        # UDP settings
        udp_config = config_data.get("udp", {}) or {}
        self.UDP_ENABLED = bool(udp_config.get("enabled", False))
        self.UDP_SEND_HZ = float(udp_config.get("send_hz", 20))
        self.UDP_TARGET1_IP = str(udp_config.get("target1_ip", "127.0.0.1"))
        self.UDP_TARGET1_PORT = int(udp_config.get("target1_port", 9005))
        self.UDP_TARGET2_IP = str(udp_config.get("target2_ip", "")) or None
        self.UDP_TARGET2_PORT = int(udp_config.get("target2_port", 9010))

    @staticmethod
    def _resolve_config_path(config_file: str) -> Path:
        """
        Resolve configuration file with compatibility:
        1) project root override: <cwd>/config.yaml
        2) package default: aruco_core/config.yaml
        """
        cwd_candidate = Path.cwd() / config_file
        package_candidate = Path(__file__).resolve().parent / config_file

        for candidate in (cwd_candidate, package_candidate):
            if candidate.exists():
                return candidate

        tried = [str(cwd_candidate), str(package_candidate)]
        raise FileNotFoundError(
            "Config file not found. Tried paths: " + ", ".join(tried)
        )


# Global configuration instance
_config_instance = None


def get_config():
    """
    Get the global configuration instance
    
    Returns:
        Config: Global configuration object
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


# For backward compatibility with old import style
def load_config():
    """Load and return configuration (creates singleton if needed)"""
    return get_config()


# Module-level attributes for direct access (backward compatibility)
def __getattr__(name):
    """
    Allow module-level attribute access like 'config.ARUCO_DICT'
    This provides backward compatibility with the old config.py
    """
    cfg = get_config()
    if hasattr(cfg, name):
        return getattr(cfg, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
