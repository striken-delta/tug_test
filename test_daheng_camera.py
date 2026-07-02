"""
大恒相机模块独立测试脚本

启动大恒相机采集画面，使用 OpenCV imshow 实时显示。
按 Q 键退出。
"""

import sys
import os
from pathlib import Path

# 将项目根目录加入 sys.path，确保能导入 aruco_core
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

# 设置大恒 SDK 环境变量 (必须在 import gxipy 之前)
_SDK_ROOT = Path(r"C:\Program Files\Daheng Imaging\GalaxySDK")
if "GALAXY_GENICAM_ROOT" not in os.environ:
    os.environ["GALAXY_GENICAM_ROOT"] = str(_SDK_ROOT / "GenICam")
if "GALAXY_GENICAM_ROOT_V64" not in os.environ:
    os.environ["GALAXY_GENICAM_ROOT_V64"] = str(_SDK_ROOT / "GenICam")
if "GALAXY_GENICAM_ROOT_V32" not in os.environ:
    os.environ["GALAXY_GENICAM_ROOT_V32"] = str(_SDK_ROOT / "GenICam")
if "GENICAM_GENTL64_PATH" not in os.environ:
    os.environ["GENICAM_GENTL64_PATH"] = str(_SDK_ROOT / "GenTL" / "Win64")
if "GENICAM_GENTL32_PATH" not in os.environ:
    os.environ["GENICAM_GENTL32_PATH"] = str(_SDK_ROOT / "GenTL" / "Win32")
if "GALAXY_GENICAM_LOG_CONFIG" not in os.environ:
    os.environ["GALAXY_GENICAM_LOG_CONFIG"] = str(_SDK_ROOT / "GenICam" / "log" / "config" / "DebugLogging.properties")
if "GALAXY_GENICAM_CACHE" not in os.environ:
    os.environ["GALAXY_GENICAM_CACHE"] = str(Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Galaxy" / "xml" / "cache")
_dll_paths = [
    str(_SDK_ROOT / "APIDll" / "Win64"),
    str(_SDK_ROOT / "APIDll" / "Win32"),
    str(_SDK_ROOT / "GenICam" / "bin" / "Win64_x64"),
    str(_SDK_ROOT / "GenICam" / "bin" / "Win32_i86"),
    str(_SDK_ROOT / "GenTL" / "Win64"),
    str(_SDK_ROOT / "GenTL" / "Win32"),
]
os.environ["PATH"] = ";".join(_dll_paths) + ";" + os.environ.get("PATH", "")
for p in _dll_paths:
    if Path(p).exists():
        os.add_dll_directory(p)

import cv2
from aruco_core.daheng_camera import DahengCamera, HAS_GXIPY
from aruco_core.config_loader import get_config


def main():
    if not HAS_GXIPY:
        print("[错误] gxipy 未安装，无法使用大恒相机", flush=True)
        print("请确认 gxipy 目录存在于项目中", flush=True)
        return

    # 读取 config.yaml 配置
    cfg = get_config()
    device_index = int(getattr(cfg, "DAHENG_DEVICE_INDEX", 1))
    exposure_time_us = float(getattr(cfg, "EXPOSURE_TIME_US", -1))
    gain_db = float(getattr(cfg, "GAIN_DB", -1))

    # 创建相机实例 (使用 config.yaml 中的曝光/增益设置)
    cam = DahengCamera(
        device_index=device_index,
        exposure_time_us=exposure_time_us,
        gain_db=gain_db,
    )

    # 列出可用设备
    print("正在搜索大恒相机设备...", flush=True)
    devices = cam.list_devices()
    if not devices:
        print("[错误] 未发现大恒相机设备", flush=True)
        return

    print(f"发现 {len(devices)} 台设备:", flush=True)
    for d in devices:
        print(f"  [{d['index']}] {d['model_name']} (SN: {d['serial_number']})", flush=True)

    # 打开相机
    print("\n正在打开相机...", flush=True)
    if not cam.open():
        print("[错误] 打开相机失败", flush=True)
        return

    print(f"相机已打开", flush=True)
    print(f"  分辨率: {cam.get(cv2.CAP_PROP_FRAME_WIDTH):.0f} x {cam.get(cv2.CAP_PROP_FRAME_HEIGHT):.0f}", flush=True)
    print(f"  FPS: {cam.get(cv2.CAP_PROP_FPS):.1f}", flush=True)
    print("\n按 Q 键退出", flush=True)

    frame_count = 0

    try:
        while True:
            ret, frame = cam.read()
            if not ret or frame is None:
                print("[警告] 采集失败")
                continue

            frame_count += 1

            # 在画面上显示帧计数
            cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2)

            cv2.imshow("Daheng Camera Test", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q'):
                break

    except KeyboardInterrupt:
        print("\n用户中断")
    finally:
        cam.release()
        cv2.destroyAllWindows()
        print(f"相机已关闭，共采集 {frame_count} 帧")


if __name__ == "__main__":
    main()
