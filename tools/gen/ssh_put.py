# -*- coding: utf-8 -*-
"""经 SSH exec 通道 base64 分块上传（绕开服务器损坏的 sftp 子系统）。

用法: python tools/gen/ssh_put.py <本地文件> <远端绝对路径>
服务端 md5 校验通过才算成功。
"""
import base64
import hashlib
import sys

sys.path.insert(0, r"F:\computing center\.workbuddy")
import ssh_exec  # noqa: E402


def put(local, remote):
    """base64 分块上传 + 服务端 md5 校验。"""
    data = open(local, "rb").read()
    b64 = base64.b64encode(data).decode()
    chunk = 48000
    parts = [b64[i:i + chunk] for i in range(0, len(b64), chunk)]
    rc, _, err = ssh_exec.run(f"rm -f '{remote}.b64'")
    assert rc == 0, err
    for i, p in enumerate(parts):
        rc, _, err = ssh_exec.run(f"printf '%s' '{p}' >> '{remote}.b64'")
        assert rc == 0, f"分块{i}失败: {err}"
    rc, out, err = ssh_exec.run(f"base64 -d '{remote}.b64' > '{remote}' && rm '{remote}.b64' && md5sum '{remote}'")
    assert rc == 0, err
    remote_md5 = out.split()[0]
    local_md5 = hashlib.md5(data).hexdigest()
    assert remote_md5 == local_md5, f"md5 不一致 {remote_md5} != {local_md5}"
    return len(data)


def main():
    local, remote = sys.argv[1], sys.argv[2]
    n = put(local, remote)
    print(f"uploaded+verified {remote} ({n} bytes)")


if __name__ == "__main__":
    main()
