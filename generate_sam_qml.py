import html

# Curated distinct colors for the 27 SAM classifications in Bhadra
# 27.0 is the main forest canopy covering ~1020 km² -> subtle translucent forest green (alpha ~0.15)
# 1.0 - 26.0 are distinct detected landcover/water/clearing features -> vibrant colors (alpha ~0.75)

colors_map = {
    27: ("46,125,50", 0.15, "Main Forest Canopy Matrix (1020 km²)", "46,125,50,120", 0.2),
    22: ("255,160,0", 0.75, "Open Land / Valley Clearing (25.5 km²)", "255,255,255,230", 0.4),
    21: ("230,81,0",  0.75, "Scrub and Rocky Ridge (11.7 km²)", "255,255,255,230", 0.4),
    19: ("0,145,234", 0.80, "Bhadra Reservoir Backwaters (6.4 km²)", "255,255,255,230", 0.4),
    17: ("118,255,3", 0.75, "Shola Grassland / Plateau (4.9 km²)", "255,255,255,230", 0.4),
    16: ("41,121,255", 0.80, "Reservoir Deep Water Bay (4.2 km²)", "255,255,255,230", 0.4),
    13: ("0,230,118", 0.75, "Riverine Corridor (1.9 km²)", "255,255,255,230", 0.4),
    12: ("0,229,255", 0.80, "Lake Inlet (1.5 km²)", "255,255,255,230", 0.4),
    10: ("255,214,0", 0.75, "Secondary Clearing (1.4 km²)", "255,255,255,230", 0.4),
    14: ("224,64,251", 0.75, "Upper Slope Ridge (1.3 km²)", "255,255,255,230", 0.4),
    9:  ("255,64,129", 0.75, "Distinct Valley Patch (1.0 km²)", "255,255,255,230", 0.4),
    8:  ("255,82,82",  0.75, "Escarpment Feature (0.98 km²)", "255,255,255,230", 0.4),
    7:  ("124,77,255", 0.75, "High Elevation Shrub (0.87 km²)", "255,255,255,230", 0.4),
    11: ("29,233,182", 0.75, "Wetland / Marsh Zone (0.52 km²)", "255,255,255,230", 0.4),
    6:  ("255,145,0",  0.75, "Hilltop Clearing (0.45 km²)", "255,255,255,230", 0.4),
    4:  ("100,221,23", 0.75, "Bamboo Brake Patch (0.35 km²)", "255,255,255,230", 0.4),
    3:  ("174,234,0",  0.75, "Forest Edge Clearing (0.29 km²)", "255,255,255,230", 0.4),
    15: ("234,128,252",0.75, "Drainage Basin Feature (0.27 km²)", "255,255,255,230", 0.4),
    20: ("0,176,255",  0.80, "Perennial Stream Pond (0.23 km²)", "255,255,255,230", 0.4),
    2:  ("255,234,0",  0.75, "Grass Clearing (0.18 km²)", "255,255,255,230", 0.4),
    1:  ("255,215,64", 0.75, "Localized Clearing (0.16 km²)", "255,255,255,230", 0.4),
    18: ("255,110,64", 0.75, "Forest Glade (0.13 km²)", "255,255,255,230", 0.4),
    26: ("208,255,0",  0.75, "Meadow Segment (0.13 km²)", "255,255,255,230", 0.4),
    24: ("105,240,174",0.75, "Riparian Patch (0.07 km²)", "255,255,255,230", 0.4),
    25: ("179,157,219",0.75, "Rock Outcrop (0.07 km²)", "255,255,255,230", 0.4),
    5:  ("255,204,128",0.75, "Micro-habitat (0.04 km²)", "255,255,255,230", 0.4),
    23: ("128,222,234",0.80, "Spring Source (0.02 km²)", "255,255,255,230", 0.4),
}

categories_xml = []
symbols_xml = []

for idx, val in enumerate(sorted(colors_map.keys())):
    rgb_str, alpha, label, outline_color, outline_w = colors_map[val]
    val_str = f"{float(val):.1f}"
    safe_label = html.escape(label)
    categories_xml.append(f'      <category symbol="{idx}" value="{val_str}" label="{safe_label}"/>')
    symbols_xml.append(f"""      <symbol type="fill" name="{idx}" alpha="{alpha}" clip_to_extent="1" force_rhr="0">
        <layer pass="0" class="SimpleFill" enabled="1" locked="0">
          <Option type="Map">
            <Option type="QString" name="border_width_map_unit_scale" value="3x:0,0,0,0,0,0"/>
            <Option type="QString" name="color" value="{rgb_str},255"/>
            <Option type="QString" name="joinstyle" value="bevel"/>
            <Option type="QString" name="offset" value="0,0"/>
            <Option type="QString" name="offset_map_unit_scale" value="3x:0,0,0,0,0,0"/>
            <Option type="QString" name="offset_unit" value="MM"/>
            <Option type="QString" name="outline_color" value="{outline_color}"/>
            <Option type="QString" name="outline_style" value="solid"/>
            <Option type="QString" name="outline_width" value="{outline_w}"/>
            <Option type="QString" name="outline_width_unit" value="MM"/>
            <Option type="QString" name="style" value="solid"/>
          </Option>
        </layer>
      </symbol>""")

qml_content = f"""<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis styleCategories="Symbology" version="3.34.0">
  <renderer-v2 attr="value" type="categorizedSymbol" symbollevels="0">
    <categories>
{chr(10).join(categories_xml)}
    </categories>
    <symbols>
{chr(10).join(symbols_xml)}
    </symbols>
  </renderer-v2>
</qgis>
"""

with open(r"C:\Users\Nehar\Desktop\HELPS\samgeo\bhadra_classifications.qml", "w", encoding="utf-8") as f:
    f.write(qml_content)

print("Generated valid bhadra_classifications.qml without unescaped XML entities!")
