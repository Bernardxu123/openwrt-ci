#!/bin/sh

# Xiaomi router SSH persistence (firewall include based).
# Fixes the upstream lemoeo/AX6S script: makes the /etc/init.d/dropbear patch
# idempotent and re-applies it on every unlock, plus resets root password.

auto_ssh_dir="/data/auto_ssh"
host_key="/etc/dropbear/dropbear_rsa_host_key"
host_key_bk="${auto_ssh_dir}/dropbear_rsa_host_key"

# Idempotent: strip the flg_ssh/channel guard out of /etc/init.d/dropbear.
# Same sed the user ran manually. Safe to re-run: once deleted the pattern no
# longer matches and nothing happens.
patch_dropbear_init() {
    [ -f /etc/init.d/dropbear ] || return 0
    sed -i '/flg_ssh=`nvram get ssh_en`/{:loop; N; /\n.*channel=`\/sbin\/uci get \/usr\/share\/xiaoqiang\/xiaoqiang_version.version.CHANNEL`\n.*return 0\n.*fi/!b loop; d}' /etc/init.d/dropbear
}

# Flip the nvram + CHANNEL unlock flags.
set_unlock_flags() {
    [ "$(nvram get telnet_en)"  = 0 ]     && { nvram set telnet_en=1;  nvram commit; }
    [ "$(nvram get ssh_en)"     = 0 ]     && { nvram set ssh_en=1;     nvram commit; }
    [ "$(nvram get uart_en)"    = 0 ]     && { nvram set uart_en=1;    nvram commit; }
    [ "$(nvram get boot_wait)"  = "off" ] && { nvram set boot_wait=on; nvram commit; }

    # Defense in depth: keep CHANNEL out of "release".
    [ "$(/sbin/uci get /usr/share/xiaoqiang/xiaoqiang_version.version.CHANNEL 2>/dev/null)" = "release" ] && {
        uci -c /usr/share/xiaoqiang set xiaoqiang_version.version.CHANNEL='stable'
        uci -c /usr/share/xiaoqiang commit xiaoqiang_version 2>/dev/null
    }
}

# Start dropbear and make it autostart on boot.
ensure_dropbear() {
    /etc/init.d/dropbear enable 2>/dev/null
    if [ -z "$(pidof dropbear)" ] || [ -z "$(netstat -ntul 2>/dev/null | grep ':22 ')" ]; then
        /etc/init.d/dropbear restart 2>/dev/null
    fi
}

# Reset root password to admin on every boot.
reset_root_password() {
    echo -e 'admin\nadmin' | passwd root >/dev/null 2>&1
}

unlock() {
    [ -f "$host_key_bk" ] && ln -sf "$host_key_bk" "$host_key"

    set_unlock_flags
    patch_dropbear_init
    ensure_dropbear

    [ -s "$host_key" ] || /etc/init.d/dropbear restart 2>/dev/null
    if [ ! -s "$host_key_bk" ]; then
        i=0
        while [ "$i" -le 30 ]; do
            [ -s "$host_key" ] && { cp -f "$host_key" "$host_key_bk" 2>/dev/null; break; }
            i=$((i+1))
            sleep 1
        done
    fi

    reset_root_password
    return 0
}

install() {
    unlock

    uci set firewall.auto_ssh=include
    uci set firewall.auto_ssh.type='script'
    uci set firewall.auto_ssh.path="${auto_ssh_dir}/auto_ssh.sh"
    uci set firewall.auto_ssh.enabled='1'
    uci commit firewall
    echo -e "\033[32m SSH unlock installed. \033[0m"
}

uninstall() {
    uci delete firewall.auto_ssh
    uci commit firewall
    echo -e "\033[33m SSH unlock removed. \033[0m"
}

main() {
    [ -z "$1" ] && { unlock; return; }
    case "$1" in
        install)
            install
            ;;
        uninstall)
            uninstall
            ;;
        *)
            echo -e "\033[31m Unknown parameter: $1 \033[0m"
            return 1
            ;;
    esac
}

main "$@"
