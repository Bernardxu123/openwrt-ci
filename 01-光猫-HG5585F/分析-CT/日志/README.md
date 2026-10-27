# 日志目录

脚本默认把日志写这里：

| 脚本 | 日志前缀 | 内容 |
|---|---|---|
| `serial-capture.ps1` | `serial-*.log` | 串口原始输出（从上下电到 login） |
| `uboot-interrupt.ps1` | `uboot-interrupt-*.log` | 抢 U-Boot 窗口时的串口输出 |
| `xmodem-send-fip.ps1` | `xmodem-*.log` | BL2 提示、握手、传输、EOT、启动输出 |

排障时优先看 `xmodem-*.log` 与 `serial-*.log` 的**开头**（BL2 版本、NAND 报错）和**结尾**（是否进 U-Boot / 是否 EOT ACK）。
求助时贴日志片段，先删掉 MAC/SN/LOID。
