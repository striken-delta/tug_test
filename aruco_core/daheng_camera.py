"""
大恒(Daheng)工业相机采集模块

基于 gxipy SDK 封装，使用零拷贝 (dq_buf/q_buf) 方式采集，
提供与 OpenCV VideoCapture 兼容的接口。
"""

import os
import threading
from pathlib import Path
import numpy as np
import cv2

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

try:
    import gxipy as gx
    from gxipy.gxidef import GxPixelFormatEntry, DxValidBit, GxFrameStatusList
    HAS_GXIPY = True
except (ImportError, KeyError, OSError):
    HAS_GXIPY = False


def _get_best_valid_bits(pixel_format):
    """根据像素格式返回最佳有效位"""
    fmt_8bit = (
        GxPixelFormatEntry.MONO8,
        GxPixelFormatEntry.BAYER_GR8, GxPixelFormatEntry.BAYER_RG8,
        GxPixelFormatEntry.BAYER_GB8, GxPixelFormatEntry.BAYER_BG8,
        GxPixelFormatEntry.RGB8, GxPixelFormatEntry.BGR8,
        GxPixelFormatEntry.R8, GxPixelFormatEntry.B8, GxPixelFormatEntry.G8,
    )
    fmt_10bit = (
        GxPixelFormatEntry.MONO10, GxPixelFormatEntry.MONO10_PACKED,
        GxPixelFormatEntry.BAYER_GR10, GxPixelFormatEntry.BAYER_RG10,
        GxPixelFormatEntry.BAYER_GB10, GxPixelFormatEntry.BAYER_BG10,
    )
    fmt_12bit = (
        GxPixelFormatEntry.MONO12, GxPixelFormatEntry.MONO12_PACKED,
        GxPixelFormatEntry.BAYER_GR12, GxPixelFormatEntry.BAYER_RG12,
        GxPixelFormatEntry.BAYER_GB12, GxPixelFormatEntry.BAYER_BG12,
    )
    fmt_16bit = (
        GxPixelFormatEntry.MONO16,
        GxPixelFormatEntry.BAYER_GR16, GxPixelFormatEntry.BAYER_RG16,
        GxPixelFormatEntry.BAYER_GB16, GxPixelFormatEntry.BAYER_BG16,
    )

    if pixel_format in fmt_8bit:
        return DxValidBit.BIT0_7
    elif pixel_format in fmt_10bit:
        return DxValidBit.BIT2_9
    elif pixel_format in fmt_12bit:
        return DxValidBit.BIT4_11
    elif pixel_format in fmt_16bit:
        return DxValidBit.BIT8_15
    return DxValidBit.BIT0_7


class DahengCamera:
    """
    大恒工业相机封装类，使用零拷贝 (dq_buf/q_buf) 采集方式。

    接口兼容 cv2.VideoCapture:
        cam = DahengCamera(device_index=1)
        cam.open()
        ret, frame = cam.read()
        cam.release()
    """

    def __init__(self, device_index=1, exposure_time_us=-1, gain_db=-1):
        """
        Args:
            device_index: 设备索引 (从1开始，与大恒SDK一致)
            exposure_time_us: 曝光时间 (微秒), -1=自动曝光
            gain_db: 增益 (dB), -1=自动增益
        """
        if not HAS_GXIPY:
            raise ImportError(
                "gxipy 未安装。请将 SDK 中的 gxipy 目录复制到项目或 Python path 中:\n"
                "  源路径: C:\\Program Files\\Daheng Imaging\\GalaxySDK\\Development\\Samples\\Python\\gxipy\n"
                "  目标: ArucoCalib/aruco_core/gxipy 或 site-packages"
            )

        self._device_index = device_index
        self._exposure_time_us = exposure_time_us
        self._gain_db = gain_db
        self._device_manager = None
        self._cam = None
        self._feature_control = None
        self._image_convert = None
        self._is_opened = False
        self._is_streaming = False
        self._is_color = None  # None=未知, True=彩色, False=黑白

        # 零拷贝: 预分配输出缓冲区，避免每帧重新分配
        self._output_buffer = None
        self._output_buffer_size = 0
        # 预分配 BGR 输出帧缓冲区，避免每帧重新分配
        self._bgr_frame = None
        self._bgr_frame_shape = None

    def open(self):
        """打开相机设备"""
        if self._is_opened:
            return True

        self._device_manager = gx.DeviceManager()
        dev_num, dev_info_list = self._device_manager.update_all_device_list()
        if dev_num == 0:
            print("[DahengCamera] 未发现大恒相机设备")
            return False

        try:
            self._cam = self._device_manager.open_device_by_index(self._device_index)
        except Exception as e:
            print(f"[DahengCamera] 打开设备失败: {e}")
            return False

        self._feature_control = self._cam.get_remote_device_feature_control()
        self._image_convert = self._device_manager.create_image_format_convert()

        # 检测彩色/黑白
        pixel_format_value, _ = self._feature_control.get_enum_feature("PixelFormat").get()
        self._is_color = not gx.Utility.is_gray(pixel_format_value)

        # 设置连续采集模式
        self._feature_control.get_enum_feature("TriggerMode").set("Off")

        # 彩色相机开启自动白平衡
        if self._is_color:
            try:
                self._feature_control.get_enum_feature("BalanceWhiteAuto").set("Continuous")
            except Exception:
                # 部分型号可能不支持，静默忽略
                pass

        # 曝光设置
        if self._exposure_time_us >= 0:
            # 手动曝光
            try:
                self._feature_control.get_enum_feature("ExposureAuto").set("Off")
                self._feature_control.get_float_feature("ExposureTime").set(float(self._exposure_time_us))
                actual = self._feature_control.get_float_feature("ExposureTime").get()
                print(f"[DahengCamera] 曝光: 手动 {actual:.1f} us")
            except Exception as e:
                print(f"[DahengCamera] 设置曝光失败: {e}")
        else:
            # 自动曝光
            try:
                self._feature_control.get_enum_feature("ExposureAuto").set("Continuous")
                print("[DahengCamera] 曝光: 自动")
            except Exception as e:
                print(f"[DahengCamera] 设置自动曝光失败: {e}")

        # 增益设置
        if self._gain_db >= 0:
            # 手动增益
            try:
                self._feature_control.get_enum_feature("GainAuto").set("Off")
                self._feature_control.get_float_feature("Gain").set(float(self._gain_db))
                actual = self._feature_control.get_float_feature("Gain").get()
                print(f"[DahengCamera] 增益: 手动 {actual:.2f} dB")
            except Exception as e:
                print(f"[DahengCamera] 设置增益失败: {e}")
        else:
            # 自动增益
            try:
                self._feature_control.get_enum_feature("GainAuto").set("Continuous")
                print("[DahengCamera] 增益: 自动")
            except Exception as e:
                print(f"[DahengCamera] 设置自动增益失败: {e}")

        self._is_opened = True
        return True

    def isOpened(self):
        """返回相机是否已打开"""
        return self._is_opened

    def read(self):
        """
        零拷贝方式采集一帧图像。

        使用 dq_buf 从 SDK 内部队列取出缓冲区，转换后立即 q_buf 归还，
        避免中间拷贝。输出缓冲区预分配复用。

        Returns:
            ret: bool, 是否成功采集
            frame: numpy.ndarray (BGR格式, 与OpenCV一致), 或 None
        """
        if not self._is_opened:
            return False, None

        # 启动数据流
        if not self._is_streaming:
            self._cam.stream_on()
            self._is_streaming = True

        data_stream = self._cam.data_stream[0]

        try:
            # 零拷贝: dq_buf 取出 SDK 内部缓冲区 (不产生数据拷贝)
            raw_image = data_stream.dq_buf(1000)
        except Exception as e:
            print(f"[DahengCamera] dq_buf 失败: {e}")
            return False, None

        if raw_image is None:
            return False, None

        try:
            if raw_image.frame_data.status != GxFrameStatusList.SUCCESS:
                return False, None

            # 转换为 BGR numpy 数组
            frame = self._raw_to_bgr(raw_image)
        finally:
            # 零拷贝: 立即 q_buf 归还缓冲区给 SDK 复用
            try:
                data_stream.q_buf(raw_image)
            except Exception:
                pass

        if frame is None:
            return False, None

        return True, frame

    def _get_output_buffer(self, size):
        """获取或复用预分配的输出缓冲区"""
        if self._output_buffer is None or self._output_buffer_size < size:
            from ctypes import c_ubyte
            self._output_buffer = (c_ubyte * size)()
            self._output_buffer_size = size
        return self._output_buffer

    def _get_bgr_frame(self, height, width):
        """获取或复用预分配的 BGR 帧缓冲区"""
        shape = (height, width, 3)
        if self._bgr_frame is None or self._bgr_frame_shape != shape:
            self._bgr_frame = np.empty(shape, dtype=np.uint8)
            self._bgr_frame_shape = shape
        return self._bgr_frame

    def _raw_to_bgr(self, raw_image):
        """
        将原始图像转换为 BGR numpy 数组。

        使用预分配缓冲区减少内存分配开销。
        所有路径均拷贝到预分配的 BGR 帧中，避免持有 SDK 内部缓冲区引用。
        """
        from ctypes import addressof

        pixel_format = raw_image.get_pixel_format()
        height = raw_image.frame_data.height
        width = raw_image.frame_data.width

        # 预分配 BGR 输出帧
        bgr_frame = self._get_bgr_frame(height, width)

        if self._is_color:
            # 彩色相机: BGR8 直接拷贝到预分配帧
            if pixel_format == GxPixelFormatEntry.BGR8:
                numpy_image = raw_image.get_numpy_array()
                if numpy_image is not None:
                    np.copyto(bgr_frame, numpy_image)
                    return bgr_frame
                return None

            # Bayer/其他 -> RGB8
            target_format = GxPixelFormatEntry.RGB8
            self._image_convert.set_dest_format(target_format)
            self._image_convert.set_valid_bits(_get_best_valid_bits(pixel_format))

            buffer_out_size = self._image_convert.get_buffer_size_for_conversion(raw_image)
            output_array = self._get_output_buffer(buffer_out_size)
            output_ptr = addressof(output_array)

            self._image_convert.convert(raw_image, output_ptr, buffer_out_size, False)

            numpy_image = np.frombuffer(output_array, dtype=np.ubyte, count=buffer_out_size)
            numpy_image = numpy_image.reshape(height, width, 3)

            # RGB -> BGR (写入预分配帧)
            cv2.cvtColor(numpy_image, cv2.COLOR_RGB2BGR, dst=bgr_frame)
            return bgr_frame
        else:
            # 黑白相机: MONO8 直接拷贝，其他格式转 MONO8
            if pixel_format in (GxPixelFormatEntry.MONO8, GxPixelFormatEntry.R8,
                                GxPixelFormatEntry.B8, GxPixelFormatEntry.G8):
                numpy_image = raw_image.get_numpy_array()
                if numpy_image is None:
                    return None
                cv2.cvtColor(numpy_image, cv2.COLOR_GRAY2BGR, dst=bgr_frame)
            else:
                target_format = GxPixelFormatEntry.MONO8
                self._image_convert.set_dest_format(target_format)
                self._image_convert.set_valid_bits(_get_best_valid_bits(pixel_format))

                buffer_out_size = self._image_convert.get_buffer_size_for_conversion(raw_image)
                output_array = self._get_output_buffer(buffer_out_size)
                output_ptr = addressof(output_array)

                self._image_convert.convert(raw_image, output_ptr, buffer_out_size, False)

                numpy_image = np.frombuffer(output_array, dtype=np.ubyte, count=buffer_out_size)
                numpy_image = numpy_image.reshape(height, width)

                cv2.cvtColor(numpy_image, cv2.COLOR_GRAY2BGR, dst=bgr_frame)

            return bgr_frame

    def get(self, prop_id):
        """
        获取相机属性 (兼容 cv2.VideoCapture.get 接口)

        Args:
            prop_id: cv2.CAP_PROP_* 常量

        Returns:
            float: 属性值
        """
        if not self._is_opened or self._feature_control is None:
            return 0.0

        try:
            if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                return float(self._feature_control.get_int_feature("Width").get())
            elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
                return float(self._feature_control.get_int_feature("Height").get())
            elif prop_id == cv2.CAP_PROP_FPS:
                return float(self._feature_control.get_float_feature("AcquisitionFrameRate").get())
            elif prop_id == cv2.CAP_PROP_EXPOSURE:
                return float(self._feature_control.get_float_feature("ExposureTime").get())
            elif prop_id == cv2.CAP_PROP_GAIN:
                return float(self._feature_control.get_float_feature("Gain").get())
        except Exception:
            pass

        return 0.0

    def set(self, prop_id, value):
        """
        设置相机属性 (兼容 cv2.VideoCapture.set 接口)

        Args:
            prop_id: cv2.CAP_PROP_* 常量
            value: 属性值

        Returns:
            bool: 是否设置成功
        """
        if not self._is_opened or self._feature_control is None:
            return False

        try:
            if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
                self._feature_control.get_int_feature("Width").set(int(value))
                return True
            elif prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
                self._feature_control.get_int_feature("Height").set(int(value))
                return True
            elif prop_id == cv2.CAP_PROP_FPS:
                self._feature_control.get_float_feature("AcquisitionFrameRate").set(float(value))
                return True
            elif prop_id == cv2.CAP_PROP_EXPOSURE:
                self._feature_control.get_enum_feature("ExposureAuto").set("Off")
                self._feature_control.get_float_feature("ExposureTime").set(float(value))
                self._exposure_time_us = float(value)
                print(f"[DahengCamera] 曝光已设为 {float(value):.1f} us")
                return True
            elif prop_id == cv2.CAP_PROP_GAIN:
                self._feature_control.get_enum_feature("GainAuto").set("Off")
                self._feature_control.get_float_feature("Gain").set(float(value))
                self._gain_db = float(value)
                print(f"[DahengCamera] 增益已设为 {float(value):.2f} dB")
                return True
        except Exception as e:
            print(f"[DahengCamera] 设置属性失败: {e}")

        return False

    def apply_exposure_gain(self, exposure_time_us=None, gain_db=None):
        """
        运行时动态修改曝光和增益，无需重启相机。

        Args:
            exposure_time_us: 曝光时间 (微秒), -1=自动, None=不修改
            gain_db: 增益 (dB), -1=自动, None=不修改
        """
        if not self._is_opened or self._feature_control is None:
            return

        if exposure_time_us is not None:
            self._exposure_time_us = exposure_time_us
            if exposure_time_us >= 0:
                try:
                    self._feature_control.get_enum_feature("ExposureAuto").set("Off")
                    self._feature_control.get_float_feature("ExposureTime").set(float(exposure_time_us))
                    actual = self._feature_control.get_float_feature("ExposureTime").get()
                    print(f"[DahengCamera] 曝光: 手动 {actual:.1f} us")
                except Exception as e:
                    print(f"[DahengCamera] 设置曝光失败: {e}")
            else:
                try:
                    self._feature_control.get_enum_feature("ExposureAuto").set("Continuous")
                    print("[DahengCamera] 曝光: 自动")
                except Exception as e:
                    print(f"[DahengCamera] 设置自动曝光失败: {e}")

        if gain_db is not None:
            self._gain_db = gain_db
            if gain_db >= 0:
                try:
                    self._feature_control.get_enum_feature("GainAuto").set("Off")
                    self._feature_control.get_float_feature("Gain").set(float(gain_db))
                    actual = self._feature_control.get_float_feature("Gain").get()
                    print(f"[DahengCamera] 增益: 手动 {actual:.2f} dB")
                except Exception as e:
                    print(f"[DahengCamera] 设置增益失败: {e}")
            else:
                try:
                    self._feature_control.get_enum_feature("GainAuto").set("Continuous")
                    print("[DahengCamera] 增益: 自动")
                except Exception as e:
                    print(f"[DahengCamera] 设置自动增益失败: {e}")

    def release(self):
        """关闭相机并释放资源"""
        if self._is_streaming and self._cam is not None:
            # 先停止采集，避免 dq_buf 持续拿到新帧
            try:
                self._feature_control.get_enum_feature("AcquisitionMode").set("Continuous")
                self._feature_control.get_command_feature("AcquisitionStop").send()
            except Exception:
                pass

            try:
                self._cam.stream_off()
            except Exception:
                pass
            self._is_streaming = False

        if self._cam is not None:
            try:
                self._cam.close_device()
            except Exception:
                pass
            self._cam = None

        self._feature_control = None
        self._image_convert = None
        self._output_buffer = None
        self._bgr_frame = None
        self._is_opened = False

    def list_devices(self):
        """
        列出所有可用的大恒相机设备

        Returns:
            list[dict]: 设备信息列表
        """
        dm = gx.DeviceManager()
        dev_num, dev_info_list = dm.update_all_device_list()
        devices = []
        for i, info in enumerate(dev_info_list):
            devices.append({
                "index": i + 1,
                "vendor_name": info.get("vendor_name", ""),
                "model_name": info.get("model_name", ""),
                "serial_number": info.get("serial_number", ""),
                "device_class": info.get("device_class", ""),
            })
        return devices

    def __del__(self):
        self.release()

    # 支持 with 语句
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False
