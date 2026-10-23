"""Make TlwgMono render Thai correctly in XeTeX (HarfBuzz):
 - Thai combining marks (and their PUA variants) -> zero advance, outline moved
   one cell (600 units) to the left so they sit over the preceding base glyph
 - drop GSUB/GPOS that only declare the 'thai' script, so HarfBuzz applies its
   built-in Thai PUA shaping (low/left/descless glyph variants)
 - rename family to "TlwgMonoTH" and record the change (GPL-2 s.2a)."""
import re, sys
from fontTools.ttLib import TTFont

MARK = re.compile(r'^uni0E(31|3[4-9A]|4[7-9A-E])(\..+)?$')
CELL = 600
styles = {'TlwgMono.ttf': ('Regular', 'TlwgMonoTH-Regular.ttf'),
          'TlwgMono-Bold.ttf': ('Bold', 'TlwgMonoTH-Bold.ttf'),
          'TlwgMono-Oblique.ttf': ('Oblique', 'TlwgMonoTH-Oblique.ttf'),
          'TlwgMono-BoldOblique.ttf': ('Bold Oblique', 'TlwgMonoTH-BoldOblique.ttf')}
src, dst = sys.argv[1], sys.argv[2]
for fn, (style, out) in styles.items():
    f = TTFont(f'{src}/{fn}')
    glyf, hmtx = f['glyf'], f['hmtx']
    marks = [g for g in f.getGlyphOrder() if MARK.match(g)]
    markset = set(marks)
    # simple glyphs first: move the outline one cell to the left
    for g in marks:
        gl = glyf[g]
        if gl.numberOfContours > 0:
            gl.coordinates.translate((-CELL, 0))
    # composites (e.g. uni0E34.left = uni0E34 shifted): move only components
    # that are not themselves marks (those were moved above)
    for g in marks:
        gl = glyf[g]
        if gl.isComposite():
            for c in gl.components:
                if c.glyphName not in markset:
                    c.x -= CELL
    for g in marks:
        gl = glyf[g]
        if gl.numberOfContours != 0:
            gl.recalcBounds(glyf)
            hmtx[g] = (0, gl.xMin)
        else:
            hmtx[g] = (0, 0)
    n = len(marks)
    for tag in ('GSUB', 'GPOS', 'hdmx', 'LTSH', 'VDMX'):
        if tag in f:
            del f[tag]
    name = f['name']
    fam = 'TlwgMonoTH'
    full = fam if style == 'Regular' else f'{fam} {style}'
    ps = fam + '-' + style.replace(' ', '')
    for rec in list(name.names):
        if rec.nameID in (1, 16):
            rec.string = fam
        elif rec.nameID == 4:
            rec.string = full
        elif rec.nameID == 6:
            rec.string = ps
        elif rec.nameID == 3:
            rec.string = f'{ps}; modified 2026-10-15'
        elif rec.nameID == 5:
            rec.string = str(rec.toUnicode()) + '; modified 2026-10-15 for CS KKU LaTeX template (zero-width Thai marks)'
    name.setName('Modified from TlwgMono (TLWG) on 2026-10-15 for the CS KKU LaTeX template: '
                 'Thai combining marks set to zero advance width; GSUB/GPOS removed so '
                 'HarfBuzz uses Thai PUA shaping. Same license as the original (GPL-2+ with font exception).',
                 10, 3, 1, 0x409)
    f.save(f'{dst}/{out}')
    print(out, 'marks fixed:', n)
