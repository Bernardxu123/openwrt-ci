# -*- coding: utf-8 -*-
"""bundle.py — 把 src/ 打包成单文件 index.html（无外部依赖，可离线双击打开）"""
import os, re, base64, io

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC  = os.path.join(ROOT, 'src')
BUILD = os.path.join(ROOT, 'build')

def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()

tpl   = read(os.path.join(SRC, 'index.template.html'))
css   = read(os.path.join(SRC, 'style.css'))
rf    = read(os.path.join(SRC, 'rf.js'))
data  = read(os.path.join(SRC, 'data.js'))
app   = read(os.path.join(SRC, 'app.js'))
assets = read(os.path.join(BUILD, 'assets.js'))

# 把 assets.js 的 export 语法去掉，改成普通 const
assets = re.sub(r'^export\s+', '', assets, flags=re.M)

js = '\n'.join([
    '/* ===== assets (plan image + wall grid) ===== */',
    assets,
    '/* ===== rf model ===== */',
    rf,
    '/* ===== data ===== */',
    data,
    '/* ===== app ===== */',
    app,
])

# 防止 </script> 提前结束
js = js.replace('</script>', '<\\/script>')

out = tpl.replace('/*__CSS__*/', css).replace('/*__JS__*/', js)
dst = os.path.join(ROOT, 'index.html')
with open(dst, 'w', encoding='utf-8') as f:
    f.write(out)

print('wrote', dst, '%.1f KB' % (len(out.encode('utf-8')) / 1024))
