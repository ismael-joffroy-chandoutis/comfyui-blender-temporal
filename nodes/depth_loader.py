# nodes/depth_loader.py

import numpy as np
import torch
import os
import re
import glob
from pathlib import Path

try:
    import OpenEXR
    import Imath
    HAS_OPENEXR = True
except ImportError:
    HAS_OPENEXR = False

try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


# ─── EXR utilities ───────────────────────────────────────────────────────────

def load_exr_channels(filepath):
    """Load all channels from an EXR file via OpenEXR. Returns (dict, width, height)."""
    if not HAS_OPENEXR:
        raise RuntimeError(
            "OpenEXR not installed. Run: pip install openexr\n"
            "On macOS: brew install openexr && pip install openexr"
        )
    exr = OpenEXR.InputFile(filepath)
    header = exr.header()
    dw = header["dataWindow"]
    w = dw.max.x - dw.min.x + 1
    h = dw.max.y - dw.min.y + 1
    pt = Imath.PixelType(Imath.PixelType.FLOAT)
    channels = {
        ch: np.frombuffer(exr.channel(ch, pt), dtype=np.float32).reshape(h, w)
        for ch in header["channels"]
    }
    exr.close()
    return channels, w, h


def load_exr_cv2(filepath):
    """Fallback EXR loader via cv2 (limited multi-channel support)."""
    if not HAS_CV2:
        raise RuntimeError("Neither OpenEXR nor cv2 available. Install openexr.")
    img = cv2.imread(filepath, cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH)
    if img is None:
        raise ValueError(f"cv2 failed to load: {filepath}")
    return img.astype(np.float32)


def hw_to_bhwc(arr):
    """Convert H×W or H×W×C numpy float32 to B×H×W×C tensor (B=1)."""
    if arr.ndim == 2:
        arr = np.stack([arr, arr, arr], axis=-1)
    return torch.from_numpy(arr.astype(np.float32)).unsqueeze(0)


# ─── Nodes ───────────────────────────────────────────────────────────────────

class BlenderEXRDepthLoader:
    """
    Load Blender's Z depth pass from EXR.

    Blender exports raw scene-unit Z distances. This node normalizes them
    to [0, 1] using your camera's near/far clipping planes, exactly what
    ControlNet depth preprocessors expect.

    Output: grayscale IMAGE (3ch) + MASK (1ch), both in [0, 1].
    """

    CATEGORY = "blender-temporal/loaders"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("depth_image", "depth_mask")
    FUNCTION = "load_depth"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "exr_path": ("STRING", {"default": "/render/depth_0001.exr", "multiline": False}),
                "near_plane": ("FLOAT", {"default": 0.1, "min": 0.001, "max": 1000.0, "step": 0.01}),
                "far_plane": ("FLOAT", {"default": 100.0, "min": 0.1, "max": 100000.0, "step": 1.0}),
                "invert": ("BOOLEAN", {"default": False}),
                "clamp": ("BOOLEAN", {"default": True}),
            }
        }

    def load_depth(self, exr_path, near_plane, far_plane, invert, clamp):
        exr_path = exr_path.strip()
        if not os.path.exists(exr_path):
            raise FileNotFoundError(f"EXR not found: {exr_path}")

        z = None
        if HAS_OPENEXR:
            channels, _, _ = load_exr_channels(exr_path)
            # Blender writes depth as 'Z'; some exporters use 'depth' or 'R'
            for name in ("Z", "z", "depth", "Depth", "R"):
                if name in channels:
                    z = channels[name]
                    break
            if z is None:
                z = list(channels.values())[0]
        else:
            raw = load_exr_cv2(exr_path)
            z = raw[:, :, 0] if raw.ndim == 3 else raw

        # Normalize to [0, 1] via near/far
        depth = (z - near_plane) / (far_plane - near_plane)

        if clamp:
            depth = np.clip(depth, 0.0, 1.0)
        if invert:
            depth = 1.0 - depth

        image = hw_to_bhwc(depth)                                    # B×H×W×3
        mask = torch.from_numpy(depth.astype(np.float32)).unsqueeze(0)  # B×H×W

        return (image, mask)


class BlenderEXRNormalLoader:
    """
    Load Blender's normal pass from EXR for ControlNet Normal conditioning.

    Blender stores normals in camera space as float RGB, values in [-1, 1].
    This node remaps them to [0, 1] and optionally flips Y to match
    OpenGL conventions expected by ControlNet normal preprocessors.
    """

    CATEGORY = "blender-temporal/loaders"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("normal_image",)
    FUNCTION = "load_normal"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "exr_path": ("STRING", {"default": "/render/normal_0001.exr", "multiline": False}),
                "coordinate_system": (["blender_camera", "opengl", "directx"],),
                "flip_y": ("BOOLEAN", {"default": True}),
            }
        }

    def load_normal(self, exr_path, coordinate_system, flip_y):
        exr_path = exr_path.strip()
        if not os.path.exists(exr_path):
            raise FileNotFoundError(f"EXR not found: {exr_path}")

        if HAS_OPENEXR:
            channels, _, _ = load_exr_channels(exr_path)
            x = next((channels[k] for k in ("NormalX", "X", "R") if k in channels), None)
            y = next((channels[k] for k in ("NormalY", "Y", "G") if k in channels), None)
            z = next((channels[k] for k in ("NormalZ", "Z", "B") if k in channels), None)
            if x is None or y is None or z is None:
                raise ValueError(
                    f"Normal channels not found. Available: {list(channels.keys())}\n"
                    "Expected: NormalX/NormalY/NormalZ or R/G/B."
                )
            normal = np.stack([x, y, z], axis=-1)  # H×W×3, range [-1, 1]
        else:
            raw = load_exr_cv2(exr_path)
            if raw.ndim < 3 or raw.shape[2] < 3:
                raise ValueError("Normal EXR must have at least 3 channels (RGB).")
            normal = raw[:, :, :3]

        if flip_y:
            normal[:, :, 1] = -normal[:, :, 1]

        # Remap [-1, 1] → [0, 1]
        normal_img = np.clip((normal + 1.0) / 2.0, 0.0, 1.0)

        return (hw_to_bhwc(normal_img),)


class BlenderPassBatchLoader:
    """
    Load a sequence of Blender EXR frames as a batch tensor.

    Reads frame_0001.exr ... frame_N.exr from a folder and returns a single
    batch IMAGE. Feed directly into temporal ControlNet workflows.
    """

    CATEGORY = "blender-temporal/loaders"
    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("batch_frames",)
    FUNCTION = "load_batch"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "folder_path": ("STRING", {"default": "/render/depth/", "multiline": False}),
                "pass_type": (["depth", "normal", "rgb"],),
                "start_frame": ("INT", {"default": 1, "min": 1, "max": 99999}),
                "end_frame": ("INT", {"default": 100, "min": 1, "max": 99999}),
            },
            "optional": {
                "near_plane": ("FLOAT", {"default": 0.1, "min": 0.001, "max": 1000.0}),
                "far_plane": ("FLOAT", {"default": 100.0, "min": 0.1, "max": 100000.0}),
                "invert_depth": ("BOOLEAN", {"default": False}),
                "flip_normal_y": ("BOOLEAN", {"default": True}),
            },
        }

    def load_batch(self, folder_path, pass_type, start_frame, end_frame,
                   near_plane=0.1, far_plane=100.0, invert_depth=False, flip_normal_y=True):
        folder_path = folder_path.strip()
        if not os.path.isdir(folder_path):
            raise NotADirectoryError(f"Folder not found: {folder_path}")

        exr_files = sorted(glob.glob(os.path.join(folder_path, "*.exr")))
        if not exr_files:
            raise FileNotFoundError(f"No EXR files in: {folder_path}")

        def frame_num(path):
            m = re.search(r"(\d+)\.exr$", os.path.basename(path))
            return int(m.group(1)) if m else -1

        frames_to_load = sorted(
            [f for f in exr_files if start_frame <= frame_num(f) <= end_frame],
            key=frame_num,
        )
        if not frames_to_load:
            raise FileNotFoundError(
                f"No EXR files for frames {start_frame}-{end_frame} in {folder_path}"
            )

        tensors = []

        if pass_type == "depth":
            loader = BlenderEXRDepthLoader()
            for f in frames_to_load:
                img, _ = loader.load_depth(f, near_plane, far_plane, invert_depth, True)
                tensors.append(img)

        elif pass_type == "normal":
            loader = BlenderEXRNormalLoader()
            for f in frames_to_load:
                (img,) = loader.load_normal(f, "blender_camera", flip_normal_y)
                tensors.append(img)

        else:  # rgb, load as-is
            for f in frames_to_load:
                if HAS_OPENEXR:
                    channels, _, _ = load_exr_channels(f)
                    vals = list(channels.values())
                    arr = np.stack((vals[:3] if len(vals) >= 3 else [vals[0]] * 3), axis=-1)
                else:
                    arr = load_exr_cv2(f)[:, :, :3]
                tensors.append(hw_to_bhwc(np.clip(arr, 0.0, 1.0)))

        return (torch.cat(tensors, dim=0),)  # B×H×W×3


class DepthNormalizer:
    """
    Normalize any depth map for ControlNet conditioning.

    Works on depth images from any source: Blender, MiDaS, ZoeDepth, Apple ARKit,
    16-bit PNGs. Three methods handle different data distributions:

    - minmax: simple linear stretch (fast, sensitive to outliers)
    - percentile: robust stretch ignoring extreme values (recommended)
    - fixed: use explicit near/far values (for matched multi-frame batches)
    """

    CATEGORY = "blender-temporal/utils"
    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("normalized_depth", "depth_mask")
    FUNCTION = "normalize"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "depth_image": ("IMAGE",),
                "method": (["minmax", "percentile", "fixed"],),
                "invert": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "near": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 10000.0}),
                "far": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10000.0}),
                "percentile_low": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 49.0}),
                "percentile_high": ("FLOAT", {"default": 98.0, "min": 51.0, "max": 100.0}),
            },
        }

    def normalize(self, depth_image, method, invert,
                  near=0.0, far=1.0, percentile_low=2.0, percentile_high=98.0):
        arr = depth_image.numpy()
        depth = arr[:, :, :, 0]  # B×H×W, take first channel

        if method == "minmax":
            lo, hi = depth.min(), depth.max()
            norm = (depth - lo) / (hi - lo) if hi - lo > 1e-8 else np.zeros_like(depth)

        elif method == "percentile":
            lo = np.percentile(depth, percentile_low)
            hi = np.percentile(depth, percentile_high)
            norm = np.clip((depth - lo) / (hi - lo), 0.0, 1.0) if hi - lo > 1e-8 else np.zeros_like(depth)

        elif method == "fixed":
            norm = np.clip((depth - near) / (far - near), 0.0, 1.0) if far - near > 1e-8 else np.zeros_like(depth)

        if invert:
            norm = 1.0 - norm

        # B×H×W×3 image + B×H×W mask
        image = torch.from_numpy(np.stack([norm, norm, norm], axis=-1).astype(np.float32))
        mask = torch.from_numpy(norm.astype(np.float32))

        return (image, mask)
