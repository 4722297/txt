# -*- coding: utf-8 -*-
from qgis.core import QgsProject
from qgis.core import Qgis

import processing


class QgisAssistant:
    """
    A class that contains the actual implementation of QGIS tool functions.
    """

    def __init__(self, iface):
        self.iface = iface

    def get_layer_context(self) -> str:
        """
        Build a structured context string describing all layers in the project.
        This gives the AI a "global view" of the map so it can choose the right layer.

        :return: A formatted string with layer info, or an error message.
        """
        root = QgsProject.instance().layerTreeRoot()
        layer_nodes = root.findLayers()

        if not layer_nodes:
            return "[No layers in the project]"

        lines = ["=== QGIS Map Layers (Top to Bottom) ==="]
        for i, node in enumerate(layer_nodes):
            layer = node.layer()
            if not layer:
                continue
            position = "Topmost" if i == 0 else f"Index {i}"
            layer_type = layer.type().name if hasattr(layer.type(), 'name') else str(layer.type())
            lines.append(
                f"[{position}] Name: '{layer.name()}', "
                f"ID: '{layer.id()}', Type: {layer_type}"
            )

        active = self.iface.activeLayer()
        if active:
            lines.append(f"\n[Currently Selected Layer] Name: '{active.name()}', ID: '{active.id()}'")
        else:
            lines.append("\n[No layer currently selected]")

        return "\n".join(lines)

    def execute_tool(self, tool_name: str, params: dict) -> str:
        """
        Dispatcher that calls the appropriate tool function.

        :param tool_name: The name of the tool to execute.
        :param params: A dictionary of parameters for the tool.
        :return: A string result message to be displayed to the user.
        """
        if hasattr(self, tool_name):
            try:
                return getattr(self, tool_name)(**params)
            except Exception as e:
                return f"Error executing tool '{tool_name}': {e}"
        else:
            return f"Error: Tool '{tool_name}' not found."

    def list_layers(self) -> str:
        """
        Lists all layers currently in the QGIS project.
        """
        layers = QgsProject.instance().mapLayers().values()
        if not layers:
            return "No layers found in the project."

        layer_names = [layer.name() for layer in layers]
        return "Available layers: <br>- " + "<br>- ".join(layer_names)

    def zoom_active_layer(self) -> str:
        """
        Zooms the map canvas to the extent of the currently active layer.
        """
        layer = self.iface.activeLayer()
        if not layer:
            return "No active layer selected. Please select a layer in the Layers panel."

        canvas = self.iface.mapCanvas()
        canvas.setExtent(layer.extent())
        canvas.refresh()
        return f"Zoomed to layer: {layer.name()}"

    def remove_layer(self, layer_name: str) -> str:
        """
        Remove a layer from the project by name or ID.

        :param layer_name: The name or ID of the layer to remove.
        :return: Result message.
        """
        project = QgsProject.instance()

        # Try by ID first
        layer = project.mapLayer(layer_name)
        if layer:
            project.removeMapLayer(layer.id())
            return f"✅ 已移除圖層: <b>{layer.name()}</b>"

        # Try by name
        layers = project.mapLayersByName(layer_name)
        if layers:
            for lyr in layers:
                project.removeMapLayer(lyr.id())
            return f"✅ 已移除圖層: <b>{layer_name}</b> ({len(layers)} 個)"

        return f"❌ 找不到圖層: '{layer_name}'"

    def rename_layer(self, layer_name: str, new_name: str) -> str:
        """
        Rename a layer by its current name or ID.

        :param layer_name: The current name or ID of the layer.
        :param new_name: The new name for the layer.
        :return: Result message.
        """
        project = QgsProject.instance()

        layer = project.mapLayer(layer_name)
        if not layer:
            layers = project.mapLayersByName(layer_name)
            layer = layers[0] if layers else None

        if not layer:
            return f"❌ 找不到圖層: '{layer_name}'"

        old_name = layer.name()
        layer.setName(new_name)
        return f"✅ 已將圖層 <b>{old_name}</b> 重新命名為 <b>{new_name}</b>"

    def toggle_layer_visibility(self, layer_name: str, visible: bool = None) -> str:
        """
        Toggle or set a layer's visibility in the layer tree.

        :param layer_name: The name or ID of the layer.
        :param visible: If provided, set to this value. If None, toggle.
        :return: Result message.
        """
        project = QgsProject.instance()
        root = project.layerTreeRoot()

        layer = project.mapLayer(layer_name)
        if not layer:
            layers = project.mapLayersByName(layer_name)
            layer = layers[0] if layers else None

        if not layer:
            return f"❌ 找不到圖層: '{layer_name}'"

        tree_layer = root.findLayer(layer.id())
        if not tree_layer:
            return f"❌ 圖層樹中找不到: '{layer_name}'"

        if visible is None:
            # Toggle
            new_state = not tree_layer.isVisible()
        else:
            new_state = visible

        tree_layer.setItemVisibilityChecked(new_state)
        state_text = "顯示" if new_state else "隱藏"
        return f"✅ 圖層 <b>{layer.name()}</b> 已{state_text}"

    def set_layer_color(self, layer_name: str, color: str) -> str:
        """
        Set the fill color of a vector layer using a simple renderer.

        :param layer_name: The name or ID of the layer.
        :param color: Color string (e.g., 'red', '#FF0000', '255,0,0').
        :return: Result message.
        """
        from qgis.core import QgsSymbol, QgsSingleSymbolRenderer
        from qgis.PyQt.QtGui import QColor

        project = QgsProject.instance()
        layer = project.mapLayer(layer_name)
        if not layer:
            layers = project.mapLayersByName(layer_name)
            layer = layers[0] if layers else None

        if not layer:
            return f"❌ 找不到圖層: '{layer_name}'"

        if not hasattr(layer, 'renderer'):
            return f"❌ 圖層 '{layer.name()}' 不是向量圖層，無法設定顏色"

        qcolor = QColor(color)
        if not qcolor.isValid():
            return f"❌ 無效的顏色: '{color}'"

        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(qcolor)
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return f"✅ 圖層 <b>{layer.name()}</b> 顏色已設為 <b>{color}</b>"

    def add_layer_from_file(self, file_path: str, layer_name: str = None) -> str:
        """
        Add a vector or raster layer from a file path.

        :param file_path: Path to the file (.shp, .gpkg, .tif, etc.).
        :param layer_name: Optional display name for the layer.
        :return: Result message.
        """
        import os
        from qgis.core import QgsVectorLayer, QgsRasterLayer

        if not os.path.exists(file_path):
            return f"❌ 檔案不存在: '{file_path}'"

        name = layer_name or os.path.splitext(os.path.basename(file_path))[0]
        ext = os.path.splitext(file_path)[1].lower()

        # Try as raster first for common raster extensions
        raster_exts = {'.tif', '.tiff', '.img', '.asc', '.nc', '.grd', '.dt2'}
        if ext in raster_exts:
            layer = QgsRasterLayer(file_path, name)
        else:
            layer = QgsVectorLayer(file_path, name, "ogr")

        if not layer.isValid():
            # Try the other type as fallback
            if ext in raster_exts:
                layer = QgsVectorLayer(file_path, name, "ogr")
            else:
                layer = QgsRasterLayer(file_path, name)

        if not layer.isValid():
            return f"❌ 無法載入檔案: '{file_path}'"

        QgsProject.instance().addMapLayer(layer)
        return f"✅ 已載入圖層: <b>{name}</b> ({ext})"

    def save_project(self) -> str:
        """
        Save the current QGIS project.

        :return: Result message.
        """
        project = QgsProject.instance()
        path = project.fileName()

        if not path:
            return "❌ 專案尚未儲存過，請先使用 QGIS 選單「另存新檔」"

        if project.write():
            return f"✅ 專案已儲存: <b>{path}</b>"
        else:
            return "❌ 儲存專案失敗"

    def open_attribute_table(self, layer_name: str) -> str:
        """
        Open the attribute table for a vector layer.
        """
        from qgis.core import Qgis
        project = QgsProject.instance()
        layer = project.mapLayer(layer_name)
        if not layer:
            layers = project.mapLayersByName(layer_name)
            layer = layers[0] if layers else None

        if not layer:
            return f"❌ 找不到圖層: '{layer_name}'"

        if layer.type() != Qgis.LayerType.Vector:
            return f"❌ 圖層 '{layer.name()}' 不是向量圖層，沒有屬性表"

        self.iface.showAttributeTable(layer)
        return f"✅ 已為圖層 <b>{layer.name()}</b> 開啟屬性表"

    def run_processing_tool(self, tool_id: str, params: dict) -> str:
        """
        Execute a QGIS Processing tool by its ID with the given parameters.

        Handles special parameter values:
        - "ACTIVE_LAYER": Replaced with the currently active layer.
        - A valid QGIS layer ID string: Replaced with the actual layer object.

        :param tool_id: The Processing tool ID (e.g., 'native:buffer').
        :param params: A dictionary of parameters for the tool.
        :return: A string result message.
        """
        resolved_params = {}
        active_layer = self.iface.activeLayer()
        project = QgsProject.instance()

        for key, value in params.items():
            if value == "ACTIVE_LAYER":
                if not active_layer:
                    return "Error: No active layer selected. Please select a layer in the Layers panel."
                resolved_params[key] = active_layer
            elif isinstance(value, str):
                # Try resolving as layer ID
                layer = project.mapLayer(value)
                if layer:
                    resolved_params[key] = layer
                else:
                    # Try resolving as layer name
                    layers_by_name = project.mapLayersByName(value)
                    if layers_by_name:
                        resolved_params[key] = layers_by_name[0]
                    else:
                        resolved_params[key] = value
            else:
                resolved_params[key] = value

        # Fallback: if INPUT is missing, use the active layer
        if "INPUT" not in resolved_params:
            if active_layer:
                resolved_params["INPUT"] = active_layer
            else:
                return "Error: No INPUT layer specified and no active layer selected."

        # Ensure OUTPUT parameter has a default value (temporary in-memory layer)
        if "OUTPUT" not in resolved_params:
            resolved_params["OUTPUT"] = "memory:"

        try:
            result = processing.run(tool_id, resolved_params)

            # Check if there's an output layer
            output_layer = result.get("OUTPUT")

            # Build a readable summary of key params (exclude INPUT/OUTPUT objects)
            param_summary = ""
            for k, v in params.items():
                if k not in ("INPUT", "OUTPUT"):
                    param_summary += f"  {k}: {v}<br>"

            if output_layer and hasattr(output_layer, 'name'):
                # Add the output layer to the project
                QgsProject.instance().addMapLayer(output_layer)
                msg = (
                    f"✅ Tool <b>{tool_id}</b> executed successfully.<br>"
                    f"Output layer: <b>{output_layer.name()}</b> has been added to the project."
                )
                if param_summary:
                    msg += f"<br>Parameters used:<br>{param_summary}"
                return msg
            else:
                return f"✅ Tool <b>{tool_id}</b> executed successfully."

        except Exception as e:
            return f"❌ Error executing tool '{tool_id}': {e}"

    def chat(self, user_input: str, provider: str = "openai",
             model: str = None, api_key: str = None,
             layer_context: str = "") -> str:
        """
        Handles general conversation by making an LLM call.
        Includes layer context so the AI can describe current map layers.
        """
        from .llm_client import query_llm

        context_section = ""
        if layer_context:
            context_section = f"\n\nCurrent map layer information:\n{layer_context}\n"

        chat_system_prompt = (
            "You are a helpful, friendly QGIS assistant. "
            "You can answer questions about GIS concepts, QGIS usage, and spatial analysis. "
            "You can also describe the layers currently loaded in the map. "
            "Respond conversationally in the same language the user used."
            f"{context_section}"
        )
        return query_llm(chat_system_prompt, user_input,
                         provider=provider, model=model, api_key=api_key)
