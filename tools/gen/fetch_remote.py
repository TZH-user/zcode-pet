# -*- coding: utf-8 -*-
"""从服务器拉文件（SFTP 损坏的替代）：exec 通道 tail|head 切块 + base64
用法: python fetch_remote.py <远端路径> <本地路径>
"""
import base64
import sys

import paramiko

HOST, USER, PWD = "192.168.20.20", "sqls", "528173973"
CHUNK = 384 * 1024


def main():
    remote, local = sys.argv[1], sys.argv[2]
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, username=USER, password=PWD, timeout=15,
                look_for_keys=False, allow_agent=False)
    _, out, _ = cli.exec_command(f"stat -c %s '{remote}'", timeout=30)
    size = int(out.read().decode().strip())
    with open(local, "wb") as f:
        off = 0
        while off < size:
            cmd = (f"tail -c +{off+1} '{remote}' | head -c {CHUNK} | base64 -w0")
            _, o2, e2 = cli.exec_command(cmd, timeout=120)
            data = o2.read().decode().strip()
            f.write(base64.b64decode(data))
            off += CHUNK
            print(f"{off}/{size}", flush=True)
    cli.close()
    print("saved", local)


if __name__ == "__main__":
    main()
