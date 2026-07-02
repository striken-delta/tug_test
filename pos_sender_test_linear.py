#!/usr/bin/env python3
import argparse
import json
import socket
import time
from typing import Tuple


def build_payload(seq: int, pos: Tuple[float, float, float], euler: Tuple[float, float, float]) -> bytes:
    data = {
        "type": "robot_position",
        "pos": [round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)],
        "euler": [round(euler[0], 2), round(euler[1], 2), round(euler[2], 2)],
        "seq": seq,
        "timestamp": time.time(),
        "holdover": False,
    }
    return json.dumps(data, sort_keys=True).encode("utf-8")

# 目标1 即是 定位数据地址 端口设置为9005   (ip是板卡地址)
# 目标2 即是 Unity的IP   端口设置为9010  （该地址先不用管）

def main():
    parser = argparse.ArgumentParser(description="发送定位测试数据：pos线性变化，euler缓慢顺时针变化")
    parser.add_argument("--target-host", type=str, default="10.168.1.246", help="目标1 IP")
    parser.add_argument("--target-port", type=int, default=9005, help="目标1 端口")
    parser.add_argument("--target-host2", type=str, default="192.168.1.104", help="目标2 IP")
    parser.add_argument("--target-port2", type=int, default=9010, help="目标2 端口")
    parser.add_argument("--hz", type=float, default=20.0, help="发送频率")
    parser.add_argument("--pos-step", type=float, default=0.005, help="每帧线性增量(米)")
    parser.add_argument("--pos-max", type=float, default=3.00, help="线性上限(米)，超过后回到0")
    parser.add_argument("--yaw-speed", type=float, default=-2, help="yaw变化速度(度/秒)，顺时针为负向")
    args = parser.parse_args()

    interval = 1.0 / max(args.hz, 0.1)
    pos_val = 0.0
    yaw = 0.0
    seq = 0
    last_t = time.perf_counter()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print("开始发送测试数据，按 Ctrl+C 停止。")
    print(f"Target1: {args.target_host}:{args.target_port}")
    print(f"Target2: {args.target_host2}:{args.target_port2}")

    try:
        while True:
            now = time.perf_counter()
            dt = now - last_t
            last_t = now

            pos_val += args.pos_step
            if pos_val > args.pos_max:
                pos_val = 0.0

            # 顺时针：yaw按负方向缓慢变化
            yaw -= args.yaw_speed * dt
            if yaw <= -180.0:
                yaw += 360.0

            pos = (pos_val, 0.0, pos_val)
            euler = (0.0, yaw, 0.0)

            seq += 1
            message = build_payload(seq, pos, euler)
            sock.sendto(message, (args.target_host, args.target_port))
            sock.sendto(message, (args.target_host2, args.target_port2))

            if seq % 20 == 0:
                print(f"seq={seq} pos={tuple(round(x, 2) for x in pos)} euler={tuple(round(x, 2) for x in euler)}")

            elapsed = time.perf_counter() - now
            if elapsed < interval:
                time.sleep(interval - elapsed)
    except KeyboardInterrupt:
        print("\n停止发送。")
    finally:
        sock.close()


if __name__ == "__main__":
    main()

