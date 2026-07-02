"""
UDP 数据发送模块

将车辆位置和航向信息通过 UDP 发送出去，格式与定位板卡协议一致。

数据格式:
    {
        "type": "robot_position",
        "pos": [x, y, z],       # 米
        "euler": [roll, pitch, yaw],  # 度
        "seq": 1,
        "timestamp": 1234567890.123,
        "holdover": false
    }
"""

import socket
import json
import time
from typing import Tuple


class UDPSender:
    """
    UDP 发送器，将车辆位姿数据以 robot_position 格式发送。

    支持双目标地址（定位板卡 + Unity），同时向两个目标发送相同数据。
    """

    def __init__(self, target1_ip="127.0.0.1", target1_port=9005,
                 target2_ip=None, target2_port=9010):
        self._targets = []
        self._targets.append((target1_ip, int(target1_port)))
        if target2_ip is not None:
            self._targets.append((target2_ip, int(target2_port)))
        self._sock = None
        self._enabled = False
        self._seq = 0

    def open(self):
        """创建 UDP socket"""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._enabled = True
            targets_str = ", ".join(f"{ip}:{port}" for ip, port in self._targets)
            print(f"[UDPSender] 已启动 -> {targets_str}")
            return True
        except Exception as e:
            print(f"[UDPSender] 创建 socket 失败: {e}")
            self._enabled = False
            return False

    def send(self, x_mm, y_mm, yaw_deg, z_mm=None, roll_deg=0.0, pitch_deg=0.0):
        """
        发送车辆位姿数据

        Args:
            x_mm: 世界坐标 X (mm)，内部转为米
            y_mm: 世界坐标 Y (mm)，内部转为米
            yaw_deg: 航向角 (度)
            z_mm: 世界坐标 Z (mm)，默认与 x_mm 相同（裁判系统要求 z≠0）
            roll_deg: 横滚角 (度)，默认 0
            pitch_deg: 俯仰角 (度)，默认 0
        """
        if not self._enabled or self._sock is None:
            return False

        if z_mm is None:
            z_mm = 20.0  # 固定 z = 0.14m（裁判系统要求 z≠0）

        self._seq += 1
        data = {
            "type": "robot_position",
            "pos": [round(x_mm / 1000.0, 2), round(z_mm / 1000.0, 2), round(y_mm / 1000.0, 2)],
            "euler": [round(roll_deg, 2), round(pitch_deg, 2), round(yaw_deg, 2)],
            "seq": self._seq,
            "timestamp": time.time(),
            "holdover": False,
        }

        try:
            msg = json.dumps(data, sort_keys=True).encode("utf-8")
            for ip, port in self._targets:
                self._sock.sendto(msg, (ip, port))
            # 每 20 包打印一次，方便与测试发送器对比
            if self._seq % 20 == 0:
                print(f"[UDPSender] seq={self._seq} json={msg.decode('utf-8')}")
            return True
        except Exception as e:
            print(f"[UDPSender] 发送失败: {e}")
            return False

    def close(self):
        """关闭 socket"""
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._enabled = False

    @property
    def enabled(self):
        return self._enabled

    def __del__(self):
        self.close()
