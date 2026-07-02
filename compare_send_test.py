#!/usr/bin/env python3
"""
对比测试：用测试发送器的代码发送与实际定位数据相同格式的数据，
验证裁判系统是否能接收。
"""
import json
import socket
import time

# 模拟我们实际发出的数据（与 udp_sender.py 完全相同的格式）
def send_our_format():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("=== 发送模拟真实定位数据 (格式与 ArucoCalib 完全一致) ===")
    print("Target: 10.168.1.246:9005, 192.168.1.104:9010")

    seq = 0
    # 模拟真实数据：pos 单位米，2位小数
    pos = (0.03, 0.02, 0.0)
    euler = (0.0, 0.0, -38.97)

    try:
        while True:
            seq += 1
            data = {
                "type": "robot_position",
                "pos": [round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)],
                "euler": [round(euler[0], 2), round(euler[1], 2), round(euler[2], 2)],
                "seq": seq,
                "timestamp": time.time(),
                "holdover": False,
            }
            msg = json.dumps(data, sort_keys=True).encode("utf-8")
            sock.sendto(msg, ("10.168.1.246", 9005))
            sock.sendto(msg, ("192.168.1.104", 9010))

            if seq % 20 == 0:
                print(f"seq={seq} msg={msg.decode('utf-8')}")

            time.sleep(0.05)  # 20Hz
    except KeyboardInterrupt:
        print("\n停止。")
    finally:
        sock.close()


if __name__ == "__main__":
    send_our_format()
