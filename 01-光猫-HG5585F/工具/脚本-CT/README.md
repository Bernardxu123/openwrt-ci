# 脚本说明

> 所有脚本默认按「本目录的上一级 = 刷机包根目录」找物料和日志。
> 运行前先 `cd` 到刷机包根目录，或直接用绝对路径。

| 脚本 | 用途 | 依赖 | 状态 |
|---|---|---|---|
| `verify-materials.ps1` | 校验 `校验/sha256sums-all.txt` 全部文件 | PowerShell | 由物料员生成 |
| `fhtool-ct.py` | `/fh_tool/api` 探测（8080→80）+ `GetDevInfo` + 自动读 MAC（`web_get_brmad`）+ 开运行时 Telnet | Python `requests`、`pycryptodome` | 算法与共享 CT V2 工具逐字一致；未在 CT 实机验证 |
| `ont-setrootpw-ct.py` | 改/还原原厂 `/tmp/shadow` 的 root 口令，为串口登录铺路 | Python（仅标准库） | 未在 CT 实机验证 |
| `serial-capture.ps1` | 串口抓日志（自动选非蓝牙 COM） | PowerShell | 同 CU 机用法 |
| `uboot-interrupt.ps1` | 上电前启动，抢 U-Boot 3 秒窗口 | PowerShell | 同 CU 机用法 |
| `xmodem-send-fip.ps1` | BL2 提示 `Press x` 后，用 XMODEM 送 CT 的 `bl31-u-boot.fip` | PowerShell | 同 CU 机用法（CU 用 v8 成功过） |

## 常用命令

```powershell
# 物料校验
pwsh -File .\脚本\verify-materials.ps1

# 只读采集：不给 MAC，自动从设备 web_get_brmad 读；默认 8080→80
python .\脚本\fhtool-ct.py 192.168.1.1

# 开运行时 Telnet（写操作；不持久化）
python .\脚本\fhtool-ct.py 192.168.1.1 --telnet-on

# 也可以手动给 MAC（贴纸/后台）
python .\脚本\fhtool-ct.py 192.168.1.1 A1B2C3D4E5F6

# 改 root 口令（telnet 口令 = admin / Fh@ + MAC 后六位）
python .\脚本\ont-setrootpw-ct.py --ip 192.168.1.1 --user admin --pass "Fh@123456" --status
python .\脚本\ont-setrootpw-ct.py --ip 192.168.1.1 --user admin --pass "Fh@123456" --set --root-password "Ct@Test2026"

# 串口
pwsh -File .\脚本\serial-capture.ps1
pwsh -File .\脚本\uboot-interrupt.ps1 -Port COM7 -Seconds 60
pwsh -File .\脚本\xmodem-send-fip.ps1 -Port COM7
```

## 注意

- `fhtool-ct.py` 的 `--telnet-on` 会写设备运行时状态（不持久化、不重启）；只在自家 LAN 用。
- `fhtool-ct.py` 不写 `cfg_cmd` 持久化；需要“重启后 Telnet 仍开”时，参考 `分析/共享资料评估.md` 的 `X_CT-COM_ServiceManage(.Lan).TelnetEnable` 两条路径，或使用共享 EXE（先 `--probe`，有风险，见评估报告）。
- `ont-setrootpw-ct.py --set` 会改原厂系统 `/tmp/shadow`（重启即还原）；它先备份到设备 `/tmp/shadow.ontbak` 和本地 `备份/shadow/`。
- 串口脚本都**不会**自动发 `x` 以外的内容；XMODEM 脚本只在看到 `Press x` 后才动。
- 若脚本报编码错误：用 PowerShell 7（`pwsh`）而不是旧版 `powershell.exe`。
