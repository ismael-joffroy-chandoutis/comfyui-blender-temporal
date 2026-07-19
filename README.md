**English** · [Français](README.fr.md)

# comfyui-blender-temporal


**ComfyUI custom nodes for loading Blender EXR depth and normal passes as ControlNet conditioning.**

Built for AI cinema production. Solves temporal consistency for long-form video generation.

<img src="monde.jpg" alt="comfyui-blender-temporal" width="100%">

---

## The problem

Every AI video tool struggles with the same thing: frame-to-frame consistency. Hair, clothes, micro-details drift between shots. LoRA helps with character identity. It does nothing for scene structure.

The actual solution is structural conditioning — feeding spatial data from 3D into the diffusion process frame by frame. Blender already generates this data. It just needs to reach ComfyUI in a usable form.

That's what this does.

---

## What it does

Blender exports depth and normal passes as EXR files. These contain raw scene data — actual Z distances in scene units, normal vectors in float RGB. Useful for 3D rendering. Incompatible with ControlNet out of the box.

These nodes bridge the gap:

```
Blender render
    │
    ├── Z depth pass (depth_0001.exr, depth_0002.exr, ...)
    │       │
    │       ▼
    │   BlenderEXRDepthLoader ──────┐
    │   (near/far normalization)    │
    │                               ▼
    └── Normal pass                ControlNet depth/normal
            │                      │
            ▼                      ▼
        BlenderEXRNormalLoader    Video generation
        (–1/1 → 0/1, flip Y)      with temporal consistency
```

For shot sequences:

```
/render/depth/
    depth_0001.exr
    depth_0002.exr     ──►  BlenderPassBatchLoader  ──►  batch IMAGE  ──►  temporal ControlNet
    depth_0003.exr
    ...
```

---

## Nodes

### `Blender EXR Depth Loader`

Loads a single Blender Z depth pass and normalizes it for ControlNet.

| Input | Type | Description |
|---|---|---|
| `exr_path` | STRING | Path to .exr file |
| `near_plane` | FLOAT | Camera near clip (Blender scene units) |
| `far_plane` | FLOAT | Camera far clip (Blender scene units) |
| `invert` | BOOLEAN | Invert depth direction |
| `clamp` | BOOLEAN | Clamp output to [0, 1] |

| Output | Type | Description |
|---|---|---|
| `depth_image` | IMAGE | 3-channel grayscale, ControlNet-ready |
| `depth_mask` | MASK | Single-channel mask |

**Near/far values:** match exactly your Blender camera clip settings (Properties → Camera → Clip Start / End).

---

### `Blender EXR Normal Loader`

Loads a single Blender normal pass and converts it for ControlNet Normal conditioning.

| Input | Type | Description |
|---|---|---|
| `exr_path` | STRING | Path to .exr file |
| `coordinate_system` | ENUM | `blender_camera` / `opengl` / `directx` |
| `flip_y` | BOOLEAN | Flip Y axis (recommended: True for most ControlNet models) |

| Output | Type | Description |
|---|---|---|
| `normal_image` | IMAGE | RGB normal map in [0, 1], ControlNet-ready |

Blender stores normals in camera space as float RGB with values in [–1, 1]. This node remaps to [0, 1] and handles axis conventions.

---

### `Blender Pass Batch Loader`

Loads an entire frame sequence from a folder as a single batch tensor.

| Input | Type | Description |
|---|---|---|
| `folder_path` | STRING | Folder containing numbered .exr files |
| `pass_type` | ENUM | `depth` / `normal` / `rgb` |
| `start_frame` | INT | First frame number to load |
| `end_frame` | INT | Last frame number to load |
| `near_plane` | FLOAT | (depth only) Camera near clip |
| `far_plane` | FLOAT | (depth only) Camera far clip |
| `invert_depth` | BOOLEAN | (depth only) Invert depth direction |
| `flip_normal_y` | BOOLEAN | (normal only) Flip Y axis |

| Output | Type | Description |
|---|---|---|
| `batch_frames` | IMAGE | B×H×W×3 batch — feed directly to temporal ControlNet |

Expects Blender's standard sequential numbering: `name_0001.exr`, `name_0002.exr`, etc.

---

### `Depth Normalizer`

Normalize any depth map for ControlNet conditioning. Works with depth images from any source.

| Input | Type | Description |
|---|---|---|
| `depth_image` | IMAGE | Any depth image |
| `method` | ENUM | `minmax` / `percentile` / `fixed` |
| `invert` | BOOLEAN | Invert depth |
| `near` / `far` | FLOAT | (fixed method) explicit range |
| `percentile_low` / `percentile_high` | FLOAT | (percentile method) outlier cutoffs |

**Methods:**
- `minmax` — linear stretch to full [0, 1] range. Fast. Sensitive to outliers.
- `percentile` — robust stretch, ignores extreme values. Recommended for real shots.
- `fixed` — explicit near/far. Use when processing matched multi-frame batches that must share the same normalization.

| Output | Type | Description |
|---|---|---|
| `normalized_depth` | IMAGE | 3-channel depth, ControlNet-ready |
| `depth_mask` | MASK | Single-channel |

---

## Installation

### Prerequisites

```bash
# macOS
brew install openexr
pip install openexr

# Linux
sudo apt install libopenexr-dev
pip install openexr

# All platforms
pip install imath numpy
```

### ComfyUI Manager

Search for `comfyui-blender-temporal` in ComfyUI Manager.

### Manual

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/ismael-joffroy-chandoutis/comfyui-blender-temporal
cd comfyui-blender-temporal
pip install -r requirements.txt
```

Restart ComfyUI. Nodes appear under `blender-temporal/` in the node browser.

---

## Blender setup

**Depth pass:**
1. Render Properties → Output → Color Depth → 32 bit
2. View Layer Properties → Passes → Data → Z
3. Compositor: Render Layers → Z socket → File Output (EXR)
4. Near/far: Camera Properties → Lens → Clip Start / End

**Normal pass:**
1. View Layer Properties → Passes → Data → Normal
2. Same compositor chain, separate output node

**Export format:** OpenEXR, not MultiLayer EXR. One pass per file.

---

## Example workflow

A minimal depth-conditioned video generation workflow:

```
BlenderPassBatchLoader
  folder_path: /renders/depth/
  pass_type: depth
  start_frame: 1
  end_frame: 120
  near_plane: 0.1
  far_plane: 50.0
        │
        ▼
ControlNetApply (depth model)
        │
        ▼
KSampler (+ your character LoRA)
        │
        ▼
VAE Decode → output frames
```

The depth pass locks scene structure. Add your character LoRA on top for identity. Result: temporally consistent AI video from Blender scene geometry.

---

## Why EXR and not depth from preprocessors (MiDaS, ZoeDepth)

Preprocessors estimate depth from the final rendered image. They don't know your scene. They fail on:
- Motion blur
- Complex lighting that flattens depth cues
- Characters in front of similarly-lit backgrounds
- Anything where the geometry is ambiguous from color alone

Blender's Z pass is ground truth — actual scene unit distances from the camera, per pixel, per frame, without estimation error. For scripted sequences where you control the 3D, there's no reason to use a preprocessor.

---

## Status

| Node | Status |
|---|---|
| BlenderEXRDepthLoader | stable |
| BlenderEXRNormalLoader | stable |
| BlenderPassBatchLoader | stable |
| DepthNormalizer | stable |

Tested with: Blender 4.1+, ComfyUI latest, ControlNet v1.1 depth/normal models.

---

## Related work

- [comfyui-cinema-pipeline](https://github.com/ismael-joffroy-chandoutis/comfyui-cinema-pipeline) — 70+ production workflows that use these nodes
- [kentskooking-nodes](https://github.com/Kentskooking/kentskooking-nodes) — wave-controlled vid2vid workflows

---

## Author

Ismaël Joffroy Chandoutis — filmmaker, César 2022. Building AI pipelines for cinema production.

[ismaeljoffroychandoutis.com](https://ismaeljoffroychandoutis.com) · [Vimeo](https://vimeo.com/ismaeljoffroychandoutis) · [Hugging Face](https://huggingface.co/12georgiadis)
