[English](README.md) · **Français**

# comfyui-blender-temporal


**Nodes personnalisés ComfyUI pour charger les passes EXR de profondeur et de normales Blender en tant que conditionnement ControlNet.**

Conçu pour la production cinéma IA. Résout la cohérence temporelle pour la génération vidéo longue.

<img src="monde.jpg" alt="comfyui-blender-temporal" width="100%">

---

## Le problème

Tous les outils vidéo IA butent sur la même chose : la cohérence image à image. Cheveux, vêtements, micro-détails dérivent d'un plan à l'autre. Le LoRA aide pour l'identité du personnage. Il ne fait rien pour la structure de la scène.

La vraie solution est le conditionnement structurel : injecter des données spatiales issues de la 3D dans le processus de diffusion, image par image. Blender génère déjà ces données. Il suffit qu'elles atteignent ComfyUI sous une forme utilisable.

C'est ce que fait cet outil.

---

## Ce que ça fait

Blender exporte les passes de profondeur et de normales sous forme de fichiers EXR. Ils contiennent des données de scène brutes : distances Z réelles en unités de scène, vecteurs normaux en RGB flottant. Utile pour le rendu 3D. Incompatible avec ControlNet en l'état.

Ces nodes font le pont :

```
Rendu Blender
    │
    ├── Passe de profondeur Z (depth_0001.exr, depth_0002.exr, ...)
    │       │
    │       ▼
    │   BlenderEXRDepthLoader ──────┐
    │   (normalisation near/far)    │
    │                               ▼
    └── Passe de normales          ControlNet depth/normal
            │                      │
            ▼                      ▼
        BlenderEXRNormalLoader    Génération vidéo
        (-1/1 → 0/1, flip Y)      avec cohérence temporelle
```

Pour des séquences de plans :

```
/render/depth/
    depth_0001.exr
    depth_0002.exr     ──►  BlenderPassBatchLoader  ──►  batch IMAGE  ──►  ControlNet temporel
    depth_0003.exr
    ...
```

---

## Nodes

### `Blender EXR Depth Loader`

Charge une passe unique de profondeur Z Blender et la normalise pour ControlNet.

| Entrée | Type | Description |
|---|---|---|
| `exr_path` | STRING | Chemin vers le fichier .exr |
| `near_plane` | FLOAT | Clip near de la caméra (unités de scène Blender) |
| `far_plane` | FLOAT | Clip far de la caméra (unités de scène Blender) |
| `invert` | BOOLEAN | Inverser la direction de la profondeur |
| `clamp` | BOOLEAN | Clamper la sortie sur [0, 1] |

| Sortie | Type | Description |
|---|---|---|
| `depth_image` | IMAGE | Niveaux de gris 3 canaux, prêt pour ControlNet |
| `depth_mask` | MASK | Masque monocanal |

**Valeurs near/far :** doivent correspondre exactement aux réglages de clip de la caméra Blender (Propriétés → Caméra → Clip Start / End).

---

### `Blender EXR Normal Loader`

Charge une passe unique de normales Blender et la convertit pour le conditionnement ControlNet Normal.

| Entrée | Type | Description |
|---|---|---|
| `exr_path` | STRING | Chemin vers le fichier .exr |
| `coordinate_system` | ENUM | `blender_camera` / `opengl` / `directx` |
| `flip_y` | BOOLEAN | Inverser l'axe Y (recommandé : True pour la plupart des modèles ControlNet) |

| Sortie | Type | Description |
|---|---|---|
| `normal_image` | IMAGE | Carte de normales RGB sur [0, 1], prête pour ControlNet |

Blender stocke les normales dans l'espace caméra en RGB flottant avec des valeurs sur [-1, 1]. Ce node les remappe sur [0, 1] et gère les conventions d'axes.

---

### `Blender Pass Batch Loader`

Charge une séquence complète d'images depuis un dossier sous forme d'un unique tenseur batch.

| Entrée | Type | Description |
|---|---|---|
| `folder_path` | STRING | Dossier contenant les fichiers .exr numérotés |
| `pass_type` | ENUM | `depth` / `normal` / `rgb` |
| `start_frame` | INT | Premier numéro d'image à charger |
| `end_frame` | INT | Dernier numéro d'image à charger |
| `near_plane` | FLOAT | (profondeur uniquement) clip near de la caméra |
| `far_plane` | FLOAT | (profondeur uniquement) clip far de la caméra |
| `invert_depth` | BOOLEAN | (profondeur uniquement) inverser la direction de la profondeur |
| `flip_normal_y` | BOOLEAN | (normales uniquement) inverser l'axe Y |

| Sortie | Type | Description |
|---|---|---|
| `batch_frames` | IMAGE | Batch B×H×W×3, à injecter directement dans un ControlNet temporel |

Suppose la numérotation séquentielle standard de Blender : `name_0001.exr`, `name_0002.exr`, etc.

---

### `Depth Normalizer`

Normalise n'importe quelle carte de profondeur pour le conditionnement ControlNet. Fonctionne avec des images de profondeur de n'importe quelle source.

| Entrée | Type | Description |
|---|---|---|
| `depth_image` | IMAGE | N'importe quelle image de profondeur |
| `method` | ENUM | `minmax` / `percentile` / `fixed` |
| `invert` | BOOLEAN | Inverser la profondeur |
| `near` / `far` | FLOAT | (méthode fixed) plage explicite |
| `percentile_low` / `percentile_high` | FLOAT | (méthode percentile) seuils d'écrêtage des valeurs aberrantes |

**Méthodes :**
- `minmax` : étirement linéaire sur la pleine plage [0, 1]. Rapide. Sensible aux valeurs aberrantes.
- `percentile` : étirement robuste, ignore les valeurs extrêmes. Recommandé pour les plans réels.
- `fixed` : near/far explicites. À utiliser quand on traite des batchs multi-images appariés qui doivent partager la même normalisation.

| Sortie | Type | Description |
|---|---|---|
| `normalized_depth` | IMAGE | Profondeur 3 canaux, prête pour ControlNet |
| `depth_mask` | MASK | Monocanal |

---

## Installation

### Prérequis

```bash
# macOS
brew install openexr
pip install openexr

# Linux
sudo apt install libopenexr-dev
pip install openexr

# Toutes plateformes
pip install imath numpy
```

### ComfyUI Manager

Chercher `comfyui-blender-temporal` dans ComfyUI Manager.

### Manuel

```bash
cd ComfyUI/custom_nodes/
git clone https://github.com/ismael-joffroy-chandoutis/comfyui-blender-temporal
cd comfyui-blender-temporal
pip install -r requirements.txt
```

Redémarrer ComfyUI. Les nodes apparaissent sous `blender-temporal/loaders` (les trois loaders EXR) et `blender-temporal/utils` (Depth Normalizer) dans le navigateur de nodes.

---

## Configuration Blender

**Passe de profondeur :**
1. Propriétés de rendu → Sortie → Profondeur de couleur → 32 bits
2. Propriétés du view layer → Passes → Data → Z
3. Compositeur : Render Layers → socket Z → File Output (EXR)
4. Near/far : Propriétés de la caméra → Objectif → Clip Start / End

**Passe de normales :**
1. Propriétés du view layer → Passes → Data → Normal
2. Même chaîne de compositeur, node de sortie séparé

**Format d'export :** OpenEXR, pas MultiLayer EXR. Une passe par fichier.

---

## Exemple de workflow

Un workflow minimal de génération vidéo conditionnée par la profondeur :

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
ControlNetApply (modèle depth)
        │
        ▼
KSampler (+ votre LoRA de personnage)
        │
        ▼
VAE Decode → images de sortie
```

La passe de profondeur verrouille la structure de la scène. Ajoutez votre LoRA de personnage par-dessus pour l'identité. Résultat : vidéo IA temporellement cohérente à partir de la géométrie de scène Blender.

---

## Pourquoi EXR et pas la profondeur des préprocesseurs (MiDaS, ZoeDepth)

Les préprocesseurs estiment la profondeur à partir de l'image rendue finale. Ils ne connaissent pas votre scène. Ils échouent sur :
- Le flou de mouvement
- Un éclairage complexe qui aplatit les indices de profondeur
- Des personnages devant des arrière-plans éclairés de façon similaire
- Tout ce dont la géométrie est ambiguë à partir de la seule couleur

La passe Z de Blender est la vérité terrain : de vraies distances en unités de scène depuis la caméra, par pixel, par image, sans erreur d'estimation. Pour des séquences scriptées où vous contrôlez la 3D, il n'y a aucune raison d'utiliser un préprocesseur.

---

## État

| Node | État |
|---|---|
| BlenderEXRDepthLoader | stable |
| BlenderEXRNormalLoader | stable |
| BlenderPassBatchLoader | stable |
| DepthNormalizer | stable |

Testé avec : Blender 4.1+, ComfyUI dernière version, modèles ControlNet v1.1 depth/normal.

---

## Travaux liés

- [comfyui-cinema-pipeline](https://github.com/ismael-joffroy-chandoutis/comfyui-cinema-pipeline) : 70+ workflows de production qui utilisent ces nodes
- [kentskooking-nodes](https://github.com/Kentskooking/kentskooking-nodes) : workflows vid2vid pilotés par ondes

---

## Licence

PolyForm Noncommercial License 1.0.0. Libre d'usage, de modification et de partage pour tout usage non commercial. L'usage commercial n'est pas autorisé. Conditions complètes dans [LICENSE.md](LICENSE.md).

## Citation

Les métadonnées de citation sont dans [CITATION.cff](CITATION.cff) ; GitHub les lit pour générer l'entrée « Citer ce dépôt ».

---

## Auteur

Ismaël Joffroy Chandoutis. Cinéaste, César 2022. Construit des pipelines IA pour la production cinéma.

[ismaeljoffroychandoutis.com](https://ismaeljoffroychandoutis.com) · [Vimeo](https://vimeo.com/user4983240) · [Hugging Face](https://huggingface.co/12georgiadis)
