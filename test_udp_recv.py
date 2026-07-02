#!/usr/bin/env python3
"""UDP 接收测试工具 - 验证 robot_position 数据是否正常发送"""

import socket
import json
import argparse


def main():
    parser = argparse.ArgumentParser(description="UDP 接收测试")
    parser.add_argument("--ip", type=str, default="0.0.0.0", help="监听 IP")
    parser.add_argument("--port", type=int, default=9005, help="监听端口")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    sock.bind((args.ip, args.port))
    print(f"监听 {args.ip}:{args.port}，等待数据... (Ctrl+C 停止)")

    try:
        while True:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
                pos = msg.get("pos", [0, 0, 0])
                euler = msg.get("euler", [0, 0, 0])
                seq = msg.get("seq", "?")
                print(f"[{addr[0]}:{addr[1]}] seq={seq} pos=({pos[0]:.4f}, {pos[1]:.4f}, {pos[2]:.4f})m  yaw={euler[2]:.2f}°")
            except json.JSONDecodeError:
                print(f"[{addr[0]}:{addr[1]}] 原始: {data}")
    except KeyboardInterrupt:
        print("\n停止监听。")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
