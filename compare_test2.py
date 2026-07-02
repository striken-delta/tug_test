#!/usr/bin/env python3
"""
二分法定位差异：分别测试两个可疑点
"""
import json
import socket
import time
import sys


def test_variant(name, pos, euler):
    """发送固定数据 3 秒，验证裁判系统是否接收"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print(f"  pos  = {pos}")
    print(f"  euler= {euler}")
    print(f"{'='*60}")

    seq = 0
    start = time.time()
    try:
        while time.time() - start < 3.0:
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
                print(f"  seq={seq} json={msg.decode('utf-8')}")

            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print(f"  已发送 {seq} 包，请检查裁判系统是否收到\n")


def main():
    choice = sys.argv[1] if len(sys.argv) > 1 else "all"

    if choice in ("1", "all"):
        # 变体1: 旋转放 index 2 (yaw)，但 z=x (模仿测试发送器的 z 模式)
        test_variant(
            "变体1: z=x, 旋转在 yaw[2] (和我们一样)",
            pos=(1.23, 0.57, 1.23),   # z=x
            euler=(0.0, 0.0, -38.97),  # 旋转在 yaw[2]
        )

    if choice in ("2", "all"):
        # 变体2: 旋转放 index 1 (pitch)，但 z=0 (和我们一样)
        test_variant(
            "变体2: z=0, 旋转在 pitch[1] (和测试发送器一样)",
            pos=(0.03, 0.02, 0.0),     # z=0
            euler=(0.0, -38.97, 0.0),   # 旋转在 pitch[1]
        )

    if choice in ("3", "all"):
        # 变体3: 完全模仿测试发送器模式 (z=x, 旋转在 pitch[1])
        test_variant(
            "变体3: z=x, 旋转在 pitch[1] (完全模仿测试发送器)",
            pos=(1.23, 0.57, 1.23),
            euler=(0.0, -38.97, 0.0),
        )

    if choice in ("4", "all"):
        # 变体4: 原始测试发送器的模式 (y=0, z=x, 旋转在 pitch[1])
        test_variant(
            "变体4: y=0, z=x, 旋转在 pitch[1] (最接近原始测试发送器)",
            pos=(1.23, 0.0, 1.23),
            euler=(0.0, -38.97, 0.0),
        )

    print("完成。请观察哪个变体被裁判系统接收。")

    if choice == "all":
        print("\n使用方式:")
        print("  python compare_test2.py 1   # 只测变体1")
        print("  python compare_test2.py 2   # 只测变体2")
        print("  python compare_test2.py 3   # 只测变体3")
        print("  python compare_test2.py 4   # 只测变体4")


if __name__ == "__main__":
    main()
