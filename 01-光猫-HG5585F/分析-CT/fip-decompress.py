import lzma, re, sys
p=r"D:\AI\路由\光猫-CT-HG5585F\物料\引导\an7581-fiberhome-hg5585f-ct-bl31-u-boot.fip"
b=open(p,"rb").read()
for name,off,size in [("bl2",0x400,0xacdc),("uboot",0xb400,0x45030)]:
    d=b[off:off+size]
    try:
        out=lzma.decompress(d,format=lzma.FORMAT_ALONE)
    except Exception as e:
        try:
            dec=lzma.LZMADecompressor(format=lzma.FORMAT_ALONE); out=dec.decompress(d)
        except Exception as e2:
            print(name,"decompress fail",e2); continue
    print(f"=== {name}: {len(d)} -> {len(out)} ===")
    t=out.decode("latin-1","replace")
    ss=[s for s in re.findall(r"[\x20-\x7e]{6,}",t) if re.search(r"Reset|reset|recovery|Recovery|HTTP|httpd|button|Button|bootcmd|bootmenu|bootdelay|U-Boot",s)]
    for s in list(dict.fromkeys(ss))[:80]:
        print(" ",s[:160])
