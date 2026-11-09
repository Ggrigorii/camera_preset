"""UIList showing stored camera presets."""

import bpy
from bpy.types import UIList


class CAMPRESET_UL_list(UIList):
    """Preset list with inline renaming and search filtering."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        row.prop(item, "name", text="", emboss=False, icon='CAMERA_DATA')

        info = row.row(align=True)
        info.alignment = 'RIGHT'
        if item.camera_type == 'PERSP' or item.camera_type == 'PANO':
            info.label(text="{:.0f}mm".format(item.lens))
        else:
            info.label(text="ortho")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = [self.bitflag_filter_item] * len(items)
        if self.filter_name:
            flags = bpy.types.UI_UL_list.filter_items_by_name(
                self.filter_name,
                self.bitflag_filter_item,
                items,
                "name",
            )
        return flags, []


classes = (CAMPRESET_UL_list,)
