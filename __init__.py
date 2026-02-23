# __init__.py

from .nodes.depth_loader import (
    BlenderEXRDepthLoader,
    BlenderEXRNormalLoader,
    BlenderPassBatchLoader,
    DepthNormalizer,
)

NODE_CLASS_MAPPINGS = {
    "BlenderEXRDepthLoader": BlenderEXRDepthLoader,
    "BlenderEXRNormalLoader": BlenderEXRNormalLoader,
    "BlenderPassBatchLoader": BlenderPassBatchLoader,
    "DepthNormalizer": DepthNormalizer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BlenderEXRDepthLoader": "Blender EXR Depth Loader",
    "BlenderEXRNormalLoader": "Blender EXR Normal Loader",
    "BlenderPassBatchLoader": "Blender Pass Batch Loader",
    "DepthNormalizer": "Depth Normalizer",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
