"""I/O, Native .ksd Format, Print-Ready CMYK PDF, Multi-Scale Slicing, Variables/Data Sets,
Actions/Batch/Image Processor, Script Events Manager, Linked Smart Objects,
Content Credentials (KinoC2PA), KinoCloud Collaboration, and GIF/MP4 Export."""
from __future__ import annotations

import base64
import csv
import datetime
import hashlib
import io
import json
import os
import zipfile
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, PngImagePlugin
from reportlab.lib.colors import CMYKColor, black
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from .engine import composite_document, rgb_to_cmyk
from .models import (
    AnimationFrame,
    Artboard,
    CommentPin,
    DocumentMetadata,
    ExtraChannel,
    KinoDocument,
    Layer,
    LayerComp,
    LayerStyles,
    PrintSettings,
    SliceRect,
    SmartFilter,
    TextLayerData,
    VectorShapeData,
)


# ---------------------------------------------------------------------------
# Helpers: PNG bytes <-> numpy RGBA
# ---------------------------------------------------------------------------
def _rgba_to_png_bytes(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    if arr.ndim == 2:
        Image.fromarray(arr, mode="L").save(buf, format="PNG")
    else:
        Image.fromarray(arr, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _png_bytes_to_array(data: bytes, mode: str = "RGBA") -> np.ndarray:
    im = Image.open(io.BytesIO(data)).convert(mode)
    return np.array(im)


def load_image_rgba(path: str) -> np.ndarray:
    """Load PNG, JPG, TIFF, WebP, BMP, GIF, ICO, or basic PSD as (H, W, 4) uint8 RGBA."""
    im = Image.open(path)
    if im.mode == "CMYK":
        im = im.convert("RGB")
    return np.array(im.convert("RGBA"))


# ---------------------------------------------------------------------------
# Content Credentials (KinoC2PA Provenance Manifest)
# ---------------------------------------------------------------------------
def build_content_credentials_manifest(doc: KinoDocument, image_rgba: np.ndarray) -> Dict[str, Any]:
    sha = hashlib.sha256(image_rgba.tobytes()).hexdigest()
    ai_used = any(bool(e.get("ai_generated", False)) for e in doc.metadata.provenance_log)
    return {
        "schema": "KinoSuite.ContentCredentials.v1",
        "claim_generator": "KinoShop 1.0 (KinoSuite for Windows)",
        "document_name": doc.name,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "asset_sha256": sha,
        "author": doc.metadata.author,
        "copyright_status": doc.metadata.copyright_status,
        "copyright_notice": doc.metadata.copyright_notice,
        "keywords": doc.metadata.keywords,
        "camera": {
            "make": doc.metadata.camera_make,
            "model": doc.metadata.camera_model,
            "lens": doc.metadata.lens,
            "iso": doc.metadata.iso,
            "aperture": doc.metadata.aperture,
            "shutter_speed": doc.metadata.shutter_speed,
            "focal_length": doc.metadata.focal_length,
        },
        "ai_assisted_or_generated": ai_used,
        "edit_actions": list(doc.metadata.provenance_log),
    }


# ---------------------------------------------------------------------------
# Native .ksd (KinoShop Document) Save & Load
# ---------------------------------------------------------------------------
def _serialize_layer(lyr: Layer, zf: zipfile.ZipFile) -> Dict[str, Any]:
    d: Dict[str, Any] = {
        "uid": lyr.uid,
        "name": lyr.name,
        "kind": lyr.kind,
        "visible": lyr.visible,
        "locked": lyr.locked,
        "opacity": lyr.opacity,
        "fill_opacity": lyr.fill_opacity,
        "blend_mode": lyr.blend_mode,
        "clipping_mask": lyr.clipping_mask,
        "offset_x": lyr.offset_x,
        "offset_y": lyr.offset_y,
        "rotation": lyr.rotation,
        "scale_x": lyr.scale_x,
        "scale_y": lyr.scale_y,
        "mask_enabled": lyr.mask_enabled,
        "adjustment_type": lyr.adjustment_type,
        "adjustment_params": lyr.adjustment_params,
        "vector_data": lyr.vector_data.to_dict() if lyr.vector_data else None,
        "text_data": lyr.text_data.to_dict() if lyr.text_data else None,
        "fill_data": lyr.fill_data,
        "styles": lyr.styles.to_dict(),
        "smart_filters": [sf.to_dict() for sf in lyr.smart_filters],
        "variable_name": lyr.variable_name,
        "linked_path": lyr.linked_path,
        "linked_mtime": lyr.linked_mtime,
        "children": [_serialize_layer(c, zf) for c in lyr.children],
    }
    if lyr.image is not None:
        key = f"layers/{lyr.uid}_img.png"
        zf.writestr(key, _rgba_to_png_bytes(lyr.image))
        d["image_ref"] = key
    if lyr.smart_source is not None:
        key = f"layers/{lyr.uid}_smart.png"
        zf.writestr(key, _rgba_to_png_bytes(lyr.smart_source))
        d["smart_ref"] = key
    if lyr.mask is not None:
        key = f"layers/{lyr.uid}_mask.png"
        zf.writestr(key, _rgba_to_png_bytes(lyr.mask))
        d["mask_ref"] = key
    return d


def _deserialize_layer(d: Dict[str, Any], zf: zipfile.ZipFile) -> Layer:
    lyr = Layer(
        uid=d.get("uid", ""),
        name=d.get("name", "Layer"),
        kind=d.get("kind", "raster"),
        visible=bool(d.get("visible", True)),
        locked=bool(d.get("locked", False)),
        opacity=float(d.get("opacity", 1.0)),
        fill_opacity=float(d.get("fill_opacity", 1.0)),
        blend_mode=d.get("blend_mode", "Normal"),
        clipping_mask=bool(d.get("clipping_mask", False)),
        offset_x=int(d.get("offset_x", 0)),
        offset_y=int(d.get("offset_y", 0)),
        rotation=float(d.get("rotation", 0.0)),
        scale_x=float(d.get("scale_x", 1.0)),
        scale_y=float(d.get("scale_y", 1.0)),
        mask_enabled=bool(d.get("mask_enabled", True)),
        adjustment_type=d.get("adjustment_type", "Levels"),
        adjustment_params=d.get("adjustment_params", {}),
        vector_data=VectorShapeData.from_dict(d["vector_data"]) if d.get("vector_data") else None,
        text_data=TextLayerData.from_dict(d["text_data"]) if d.get("text_data") else None,
        fill_data=d.get("fill_data", {}),
        styles=LayerStyles.from_dict(d.get("styles", {})),
        smart_filters=[SmartFilter.from_dict(sf) for sf in d.get("smart_filters", [])],
        variable_name=d.get("variable_name", ""),
        linked_path=d.get("linked_path", ""),
        linked_mtime=float(d.get("linked_mtime", 0.0)),
        children=[_deserialize_layer(c, zf) for c in d.get("children", [])],
    )
    if d.get("image_ref") and d["image_ref"] in zf.namelist():
        lyr.image = _png_bytes_to_array(zf.read(d["image_ref"]), "RGBA")
    if d.get("smart_ref") and d["smart_ref"] in zf.namelist():
        lyr.smart_source = _png_bytes_to_array(zf.read(d["smart_ref"]), "RGBA")
    if d.get("mask_ref") and d["mask_ref"] in zf.namelist():
        lyr.mask = _png_bytes_to_array(zf.read(d["mask_ref"]), "L")
    return lyr


def save_ksd(doc: KinoDocument, path: str) -> None:
    """Save complete layered KinoShop Document (.ksd)."""
    doc.metadata.record_provenance("Saved KSD", details=os.path.basename(path))
    comp = composite_document(doc, apply_view_effects=False)
    creds = build_content_credentials_manifest(doc, comp)

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        layers_meta = [_serialize_layer(l, zf) for l in doc.layers]
        ch_meta = []
        for ec in doc.extra_channels:
            cdict = {
                "uid": ec.uid,
                "name": ec.name,
                "kind": ec.kind,
                "color": list(ec.color),
                "solidity": ec.solidity,
                "visible": ec.visible,
            }
            if ec.data is not None:
                key = f"channels/{ec.uid}.png"
                zf.writestr(key, _rgba_to_png_bytes(ec.data))
                cdict["data_ref"] = key
            ch_meta.append(cdict)

        manifest = {
            "format": "KinoShopDocument",
            "version": 1,
            "uid": doc.uid,
            "name": doc.name,
            "width": doc.width,
            "height": doc.height,
            "dpi": doc.dpi,
            "color_mode": doc.color_mode,
            "bit_depth": doc.bit_depth,
            "color_profile": doc.color_profile,
            "active_layer_id": doc.active_layer_id,
            "guides_h": doc.guides_h,
            "guides_v": doc.guides_v,
            "artboards": [a.to_dict() for a in doc.artboards],
            "slices": [s.to_dict() for s in doc.slices],
            "print_settings": doc.print_settings.to_dict(),
            "frames": [f.to_dict() for f in doc.frames],
            "timeline_fps": doc.timeline_fps,
            "variables_map": doc.variables_map,
            "data_sets": doc.data_sets,
            "comments": [c.to_dict() for c in doc.comments],
            "layer_comps": [lc.to_dict() for lc in doc.layer_comps],
            "metadata": doc.metadata.to_dict(),
            "layers": layers_meta,
            "extra_channels": ch_meta,
        }
        zf.writestr("document.json", json.dumps(manifest, indent=2))
        zf.writestr("preview.png", _rgba_to_png_bytes(comp))
        zf.writestr("content_credentials.json", json.dumps(creds, indent=2))

    doc.file_path = path
    doc.name = os.path.basename(path)
    doc.dirty = False


def load_ksd(path: str) -> KinoDocument:
    """Load a layered KinoShop Document (.ksd)."""
    with zipfile.ZipFile(path, "r") as zf:
        manifest = json.loads(zf.read("document.json").decode("utf-8"))
        doc = KinoDocument(
            width=int(manifest.get("width", 1280)),
            height=int(manifest.get("height", 800)),
            name=os.path.basename(path),
            dpi=int(manifest.get("dpi", 300)),
            color_mode=manifest.get("color_mode", "RGB"),
            color_profile=manifest.get("color_profile", "sRGB IEC61966-2.1"),
        )
        doc.uid = manifest.get("uid", doc.uid)
        doc.bit_depth = int(manifest.get("bit_depth", 8))
        doc.layers = [_deserialize_layer(ld, zf) for ld in manifest.get("layers", [])]
        doc.active_layer_id = manifest.get("active_layer_id") or (doc.layers[-1].uid if doc.layers else None)
        doc.guides_h = list(manifest.get("guides_h", []))
        doc.guides_v = list(manifest.get("guides_v", []))
        doc.artboards = [Artboard.from_dict(a) for a in manifest.get("artboards", [])] or doc.artboards
        doc.slices = [SliceRect.from_dict(s) for s in manifest.get("slices", [])]
        doc.print_settings = PrintSettings.from_dict(manifest.get("print_settings", {}))
        doc.frames = [AnimationFrame.from_dict(f) for f in manifest.get("frames", [])]
        doc.timeline_fps = float(manifest.get("timeline_fps", 12.0))
        doc.variables_map = dict(manifest.get("variables_map", {}))
        doc.data_sets = list(manifest.get("data_sets", []))
        doc.comments = [CommentPin.from_dict(c) for c in manifest.get("comments", [])]
        doc.layer_comps = [LayerComp.from_dict(lc) for lc in manifest.get("layer_comps", [])]
        if manifest.get("metadata"):
            doc.metadata = DocumentMetadata.from_dict(manifest["metadata"])
        doc.extra_channels = []
        for cd in manifest.get("extra_channels", []):
            data = _png_bytes_to_array(zf.read(cd["data_ref"]), "L") if cd.get("data_ref") in zf.namelist() else None
            doc.extra_channels.append(
                ExtraChannel(
                    uid=cd.get("uid", ""),
                    name=cd.get("name", "Alpha"),
                    kind=cd.get("kind", "alpha"),
                    color=tuple(cd.get("color", [255, 0, 85])),
                    solidity=float(cd.get("solidity", 0.5)),
                    visible=bool(cd.get("visible", False)),
                    data=data,
                )
            )
        doc.file_path = path
        doc.dirty = False
        doc.history.clear()
        doc.snapshots.clear()
        doc.history_index = -1
        doc.push_history("Opened Document", is_snapshot=True)
        return doc


# ---------------------------------------------------------------------------
# Linked Smart Object Updater
# ---------------------------------------------------------------------------
def update_linked_smart_objects(doc: KinoDocument, force: bool = False) -> int:
    """Reload any Linked Smart Object whose external file changed on disk. Returns updated count."""
    updated = 0
    for lyr in doc.iter_all_layers():
        if lyr.kind == "smart_object" and lyr.linked_path and os.path.isfile(lyr.linked_path):
            mtime = os.path.getmtime(lyr.linked_path)
            if force or mtime > lyr.linked_mtime + 1e-4:
                try:
                    if lyr.linked_path.lower().endswith(".ksd"):
                        sub_doc = load_ksd(lyr.linked_path)
                        lyr.smart_source = composite_document(sub_doc, apply_view_effects=False)
                    else:
                        lyr.smart_source = load_image_rgba(lyr.linked_path)
                    lyr.linked_mtime = mtime
                    updated += 1
                except Exception:
                    pass
    if updated > 0:
        doc.dirty = True
    return updated


# ---------------------------------------------------------------------------
# Multi-Format Export: PNG, JPEG, TIFF, WebP, BMP, ICO, SVG, Print CMYK PDF
# ---------------------------------------------------------------------------
def export_image(
    doc: KinoDocument,
    path: str,
    quality: int = 92,
    scale: float = 1.0,
    embed_credentials: bool = True,
) -> None:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".ksd":
        save_ksd(doc, path)
        return
    if ext == ".pdf":
        export_print_pdf(doc, path)
        return
    if ext == ".svg":
        export_svg(doc, path)
        return

    rgba = composite_document(doc, apply_view_effects=False)
    if abs(scale - 1.0) > 1e-3:
        nw = max(1, int(round(rgba.shape[1] * scale)))
        nh = max(1, int(round(rgba.shape[0] * scale)))
        rgba = cv2.resize(rgba, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC)

    pil = Image.fromarray(rgba, mode="RGBA")
    doc.metadata.record_provenance("Exported Image", details=f"{os.path.basename(path)} ({ext})")
    creds_json = json.dumps(build_content_credentials_manifest(doc, rgba)) if embed_credentials else ""

    if ext == ".png":
        info = PngImagePlugin.PngInfo()
        if doc.metadata.author:
            info.add_text("Author", doc.metadata.author)
        if doc.metadata.copyright_notice:
            info.add_text("Copyright", doc.metadata.copyright_notice)
        if doc.metadata.keywords:
            info.add_text("Keywords", doc.metadata.keywords)
        if creds_json:
            info.add_text("KinoC2PA", creds_json)
        pil.save(path, format="PNG", pnginfo=info, dpi=(doc.dpi, doc.dpi))
    elif ext in (".jpg", ".jpeg"):
        rgb = pil.convert("RGB")
        if doc.color_mode == "CMYK":
            pil.convert("CMYK").save(path, format="JPEG", quality=quality, dpi=(doc.dpi, doc.dpi))
        else:
            rgb.save(path, format="JPEG", quality=quality, dpi=(doc.dpi, doc.dpi))
    elif ext in (".tif", ".tiff"):
        out_im = pil.convert("CMYK") if doc.color_mode == "CMYK" else pil
        out_im.save(path, format="TIFF", dpi=(doc.dpi, doc.dpi))
    elif ext == ".webp":
        pil.save(path, format="WEBP", quality=quality)
    elif ext == ".bmp":
        pil.convert("RGB").save(path, format="BMP")
    elif ext == ".ico":
        pil.save(path, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    else:
        pil.save(path)


def export_svg(doc: KinoDocument, path: str) -> None:
    """Export vector shapes, text layers, and raster layers cleanly to SVG."""
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{doc.width}" height="{doc.height}" viewBox="0 0 {doc.width} {doc.height}">',
        f'  <!-- Generated by KinoShop 1.0 ({doc.name}) -->',
    ]
    for lyr in doc.layers:
        if not lyr.visible:
            continue
        op = f' opacity="{lyr.opacity:.3f}"' if lyr.opacity < 0.999 else ""
        if lyr.kind == "vector" and lyr.vector_data is not None:
            vd = lyr.vector_data
            x, y, w, h = vd.rect
            fill = f"rgba({vd.fill_color[0]},{vd.fill_color[1]},{vd.fill_color[2]},{vd.fill_color[3]/255:.2f})" if vd.fill_enabled else "none"
            stroke = f"rgba({vd.stroke_color[0]},{vd.stroke_color[1]},{vd.stroke_color[2]},{vd.stroke_color[3]/255:.2f})" if vd.stroke_enabled else "none"
            if vd.shape_type == "ellipse":
                parts.append(f'  <ellipse cx="{x+w/2:.1f}" cy="{y+h/2:.1f}" rx="{w/2:.1f}" ry="{h/2:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{vd.stroke_width}"{op}/>')
            elif vd.shape_type in ("rectangle", "rounded_rect"):
                rx = vd.corner_radius if vd.shape_type == "rounded_rect" else 0
                parts.append(f'  <rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" fill="{fill}" stroke="{stroke}" stroke-width="{vd.stroke_width}"{op}/>')
            elif vd.shape_type == "path" and vd.points:
                d_str = "M " + " L ".join(f"{px:.1f},{py:.1f}" for px, py in vd.points) + (" Z" if vd.closed else "")
                parts.append(f'  <path d="{d_str}" fill="{fill}" stroke="{stroke}" stroke-width="{vd.stroke_width}"{op}/>')
        elif lyr.kind == "text" and lyr.text_data is not None:
            td = lyr.text_data
            col = f"rgb({td.color[0]},{td.color[1]},{td.color[2]})"
            fw = "bold" if td.bold else "normal"
            esc = td.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f'  <text x="{td.x:.1f}" y="{td.y:.1f}" font-family="{td.font_family}" font-size="{td.font_size}" font-weight="{fw}" fill="{col}"{op}>{esc}</text>')
        elif lyr.image is not None:
            b64 = base64.b64encode(_rgba_to_png_bytes(lyr.image)).decode("ascii")
            parts.append(f'  <image x="{lyr.offset_x}" y="{lyr.offset_y}" width="{lyr.image.shape[1]}" height="{lyr.image.shape[0]}" href="data:image/png;base64,{b64}"{op}/>')
    parts.append("</svg>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


def export_print_pdf(doc: KinoDocument, path: str) -> None:
    """Export Print-Ready CMYK PDF with configurable Bleed, Crop Marks, Registration Targets & CMYK Color Bars."""
    ps = doc.print_settings
    trim_w_pt = doc.width / max(doc.dpi, 72) * 72.0
    trim_h_pt = doc.height / max(doc.dpi, 72) * 72.0
    bleed_pt = ps.bleed_mm / 25.4 * 72.0
    slug_pt = 28.0 if (ps.crop_marks or ps.registration_marks or ps.color_bars or ps.page_info) else 0.0

    page_w = trim_w_pt + 2 * (bleed_pt + slug_pt)
    page_h = trim_h_pt + 2 * (bleed_pt + slug_pt)

    c = rl_canvas.Canvas(path, pagesize=(page_w, page_h))
    c.setTitle(doc.metadata.title or doc.name)
    c.setAuthor(doc.metadata.author or "KinoShop")

    rgba = composite_document(doc, apply_view_effects=False)
    pil = Image.fromarray(rgba, mode="RGBA")
    # Convert to CMYK JPEG buffer for true CMYK press output
    cmyk_im = pil.convert("CMYK") if doc.color_mode == "CMYK" or ps.soft_proof else pil.convert("RGB")
    buf = io.BytesIO()
    cmyk_im.save(buf, format="JPEG", quality=96)
    buf.seek(0)

    # Draw image extended into bleed box
    img_x = slug_pt
    img_y = slug_pt
    img_w = trim_w_pt + 2 * bleed_pt
    img_h = trim_h_pt + 2 * bleed_pt
    c.drawImage(ImageReader(buf), img_x, img_y, width=img_w, height=img_h)

    # Trim box coordinates
    tx0 = slug_pt + bleed_pt
    ty0 = slug_pt + bleed_pt
    tx1 = tx0 + trim_w_pt
    ty1 = ty0 + trim_h_pt

    if ps.crop_marks:
        c.setStrokeColor(CMYKColor(1, 1, 1, 1))  # Registration black
        c.setLineWidth(0.5)
        ml = 14.0
        gap = 4.0
        for (cx, cy, sx, sy) in [
            (tx0, ty0, -1, -1), (tx1, ty0, 1, -1), (tx0, ty1, -1, 1), (tx1, ty1, 1, 1),
        ]:
            c.line(cx + sx * gap, cy, cx + sx * (gap + ml), cy)
            c.line(cx, cy + sy * gap, cx, cy + sy * (gap + ml))

    if ps.registration_marks:
        c.setStrokeColor(CMYKColor(1, 1, 1, 1))
        c.setLineWidth(0.5)
        for rx, ry in [(page_w * 0.5, slug_pt * 0.5), (page_w * 0.5, page_h - slug_pt * 0.5)]:
            c.circle(rx, ry, 5.0)
            c.line(rx - 8, ry, rx + 8, ry)
            c.line(rx, ry - 8, rx, ry + 8)

    if ps.color_bars:
        swatches = [
            CMYKColor(1, 0, 0, 0), CMYKColor(0, 1, 0, 0), CMYKColor(0, 0, 1, 0), CMYKColor(0, 0, 0, 1),
            CMYKColor(0.5, 0, 0, 0), CMYKColor(0, 0.5, 0, 0), CMYKColor(0, 0, 0.5, 0), CMYKColor(0, 0, 0, 0.5),
        ]
        bx = tx0
        by = page_h - slug_pt * 0.72
        for sw in swatches:
            c.setFillColor(sw)
            c.setStrokeColor(black)
            c.setLineWidth(0.25)
            c.rect(bx, by, 14, 9, fill=1, stroke=1)
            bx += 15

    if ps.page_info:
        c.setFillColor(black)
        c.setFont("Helvetica", 6.5)
        info = f"{doc.name}  |  {doc.color_mode} ({doc.color_profile})  |  {doc.dpi} DPI  |  Bleed {ps.bleed_mm:.1f}mm  |  KinoShop"
        c.drawString(tx0, 6.0, info)

    c.showPage()
    c.save()


# ---------------------------------------------------------------------------
# Slicing & Multi-Scale Web Asset Export
# ---------------------------------------------------------------------------
def export_slices_multiscale(doc: KinoDocument, out_dir: str, quality: int = 90) -> List[str]:
    """Export every slice (or artboard if no slices) at all configured scales (1x, 2x, 3x)."""
    os.makedirs(out_dir, exist_ok=True)
    comp = composite_document(doc, apply_view_effects=False)
    h, w = comp.shape[:2]
    items = doc.slices if doc.slices else [
        SliceRect(name=ab.name.replace(" ", "_"), x=ab.x, y=ab.y, width=ab.width, height=ab.height, fmt="PNG", scales=[1.0, 2.0])
        for ab in doc.artboards
    ]
    written: List[str] = []
    for sl in items:
        x0 = max(0, min(w - 1, sl.x))
        y0 = max(0, min(h - 1, sl.y))
        x1 = max(x0 + 1, min(w, sl.x + sl.width))
        y1 = max(y0 + 1, min(h, sl.y + sl.height))
        crop = comp[y0:y1, x0:x1]
        for sc in sl.scales:
            cw = max(1, int(round(crop.shape[1] * sc)))
            ch = max(1, int(round(crop.shape[0] * sc)))
            resized = cv2.resize(crop, (cw, ch), interpolation=cv2.INTER_CUBIC if sc > 1.0 else cv2.INTER_AREA)
            suffix = "" if abs(sc - 1.0) < 0.01 else f"@{int(sc) if sc == int(sc) else sc}x"
            ext = sl.fmt.lower().replace("jpeg", "jpg")
            fname = f"{sl.name}{suffix}.{ext}"
            fpath = os.path.join(out_dir, fname)
            pil = Image.fromarray(resized, mode="RGBA")
            if ext == "jpg":
                pil.convert("RGB").save(fpath, format="JPEG", quality=quality)
            elif ext == "webp":
                pil.save(fpath, format="WEBP", quality=quality)
            else:
                pil.save(fpath, format="PNG")
            written.append(fpath)
    return written


# ---------------------------------------------------------------------------
# Variables & Data Sets Batch Generator (from CSV Spreadsheet)
# ---------------------------------------------------------------------------
def load_csv_datasets(csv_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        cols = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return cols, rows


def apply_dataset_to_doc(doc: KinoDocument, row: Dict[str, str]) -> None:
    """Apply a single spreadsheet row to bound Text, Visibility, or Image layers."""
    for lyr in doc.iter_all_layers():
        col = doc.variables_map.get(lyr.uid) or lyr.variable_name
        if not col or col not in row:
            continue
        val = row[col]
        if lyr.kind == "text" and lyr.text_data is not None:
            lyr.text_data.text = val
        elif val.lower() in ("true", "false", "1", "0", "yes", "no"):
            lyr.visible = val.lower() in ("true", "1", "yes")
        elif os.path.isfile(val):
            try:
                img = load_image_rgba(val)
                img = cv2.resize(img, (doc.width, doc.height), interpolation=cv2.INTER_AREA)
                if lyr.kind == "smart_object":
                    lyr.smart_source = img
                else:
                    lyr.image = img
            except Exception:
                pass


def batch_export_datasets(doc: KinoDocument, out_dir: str, fmt: str = "PNG") -> List[str]:
    """Generate a full batch of design variations from all loaded CSV Data Sets."""
    os.makedirs(out_dir, exist_ok=True)
    saved_layers = [l.clone() for l in doc.layers]
    outputs: List[str] = []
    ext = fmt.lower().replace("jpeg", "jpg")
    try:
        for idx, row in enumerate(doc.data_sets, start=1):
            doc.layers = [l.clone() for l in saved_layers]
            apply_dataset_to_doc(doc, row)
            slug = f"variant_{idx:03d}"
            out_path = os.path.join(out_dir, f"{slug}.{ext}")
            export_image(doc, out_path)
            outputs.append(out_path)
    finally:
        doc.layers = saved_layers
    return outputs


# ---------------------------------------------------------------------------
# Image Processor (Batch Format Conversion & Resize)
# ---------------------------------------------------------------------------
def run_image_processor(
    src_dir: str,
    out_dir: str,
    formats: List[str],
    max_w: int = 0,
    max_h: int = 0,
    quality: int = 90,
    copyright_text: str = "",
) -> List[str]:
    """Batch convert all images in src_dir into one or more formats & dimensions."""
    os.makedirs(out_dir, exist_ok=True)
    exts = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".ksd")
    written: List[str] = []
    for fname in sorted(os.listdir(src_dir)):
        if not fname.lower().endswith(exts):
            continue
        fpath = os.path.join(src_dir, fname)
        stem = os.path.splitext(fname)[0]
        try:
            if fname.lower().endswith(".ksd"):
                d = load_ksd(fpath)
                rgba = composite_document(d, apply_view_effects=False)
            else:
                rgba = load_image_rgba(fpath)
        except Exception:
            continue

        if max_w > 0 and max_h > 0:
            h, w = rgba.shape[:2]
            sc = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
            if sc < 0.999:
                rgba = cv2.resize(rgba, (max(1, int(w * sc)), max(1, int(h * sc))), interpolation=cv2.INTER_AREA)

        pil = Image.fromarray(rgba, mode="RGBA")
        for fmt in formats:
            fext = fmt.lower().replace("jpeg", "jpg")
            sub = os.path.join(out_dir, fmt.upper())
            os.makedirs(sub, exist_ok=True)
            out_path = os.path.join(sub, f"{stem}.{fext}")
            if fext == "jpg":
                pil.convert("RGB").save(out_path, format="JPEG", quality=quality)
            elif fext == "webp":
                pil.save(out_path, format="WEBP", quality=quality)
            elif fext == "tiff":
                pil.save(out_path, format="TIFF")
            else:
                info = PngImagePlugin.PngInfo()
                if copyright_text:
                    info.add_text("Copyright", copyright_text)
                pil.save(out_path, format="PNG", pnginfo=info)
            written.append(out_path)
    return written


# ---------------------------------------------------------------------------
# Animation GIF & Basic Video Timeline Export / Import
# ---------------------------------------------------------------------------
def render_animation_frames(doc: KinoDocument) -> List[Tuple[np.ndarray, int]]:
    """Render every frame in doc.frames to (RGBA, duration_ms)."""
    if not doc.frames:
        return [(composite_document(doc, apply_view_effects=False), 120)]
    saved = [l.clone() for l in doc.layers]
    out: List[Tuple[np.ndarray, int]] = []
    try:
        for fr in doc.frames:
            if fr.video_frame is not None:
                out.append((fr.video_frame, fr.duration_ms))
                continue
            for lyr in doc.iter_all_layers():
                if lyr.uid in fr.layer_visibility:
                    lyr.visible = fr.layer_visibility[lyr.uid]
                if lyr.uid in fr.layer_offsets:
                    lyr.offset_x, lyr.offset_y = fr.layer_offsets[lyr.uid]
                if lyr.uid in fr.layer_opacities:
                    lyr.opacity = fr.layer_opacities[lyr.uid]
            out.append((composite_document(doc, apply_view_effects=False), max(20, fr.duration_ms)))
    finally:
        doc.layers = saved
    return out


def export_animated_gif(doc: KinoDocument, path: str) -> None:
    frames = render_animation_frames(doc)
    pils = [Image.fromarray(rgba, mode="RGBA").convert("P", palette=Image.Palette.ADAPTIVE) for rgba, _ in frames]
    durs = [d for _, d in frames]
    pils[0].save(path, save_all=True, append_images=pils[1:], duration=durs, loop=0, optimize=False)


def export_video_mp4(doc: KinoDocument, path: str, fps: float = 12.0) -> None:
    frames = render_animation_frames(doc)
    h, w = doc.height, doc.width
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(path, fourcc, max(1.0, fps), (w, h))
    for rgba, _ in frames:
        bgr = cv2.resize(rgba[..., :3], (w, h))[..., ::-1]
        writer.write(bgr)
    writer.release()


def import_video_to_frames(video_path: str, max_frames: int = 90) -> Tuple[List[np.ndarray], float]:
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames: List[np.ndarray] = []
    while len(frames) < max_frames:
        ok, bgr = cap.read()
        if not ok:
            break
        rgb = bgr[..., ::-1]
        rgba = np.dstack([rgb, np.full(rgb.shape[:2], 255, dtype=np.uint8)])
        frames.append(rgba)
    cap.release()
    return frames, float(fps)


# ---------------------------------------------------------------------------
# KinoCloud Collaboration (Cloud Docs, Version History & Share-for-Review HTML)
# ---------------------------------------------------------------------------
class KinoCloudManager:
    """Manages local KinoCloud versioned documents, comments & shareable HTML review packages."""

    def __init__(self, root_dir: str) -> None:
        self.root = os.path.join(root_dir, ".kinocloud")
        os.makedirs(self.root, exist_ok=True)

    def _doc_dir(self, doc: KinoDocument) -> str:
        cid = doc.cloud_id or doc.uid
        doc.cloud_id = cid
        d = os.path.join(self.root, cid)
        os.makedirs(d, exist_ok=True)
        return d

    def save_cloud_version(self, doc: KinoDocument, note: str = "Checkpoint") -> Dict[str, Any]:
        ddir = self._doc_dir(doc)
        idx_path = os.path.join(ddir, "versions.json")
        versions = json.loads(open(idx_path, "r", encoding="utf-8").read()) if os.path.isfile(idx_path) else []
        vnum = len(versions) + 1
        fname = f"v{vnum:03d}.ksd"
        fpath = os.path.join(ddir, fname)
        save_ksd(doc, fpath)
        entry = {
            "version": vnum,
            "file": fname,
            "note": note,
            "author": doc.metadata.author,
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "comments_count": len(doc.comments),
        }
        versions.append(entry)
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(versions, f, indent=2)
        return entry

    def list_versions(self, doc: KinoDocument) -> List[Dict[str, Any]]:
        ddir = self._doc_dir(doc)
        idx_path = os.path.join(ddir, "versions.json")
        if not os.path.isfile(idx_path):
            return []
        return json.loads(open(idx_path, "r", encoding="utf-8").read())

    def load_version(self, doc: KinoDocument, version_file: str) -> KinoDocument:
        ddir = self._doc_dir(doc)
        loaded = load_ksd(os.path.join(ddir, version_file))
        loaded.cloud_id = doc.cloud_id
        return loaded

    def export_share_for_review_html(self, doc: KinoDocument, out_html: str) -> str:
        """Create a sleek standalone KinoCloud Share-for-Review HTML page with pinned comments & credentials."""
        comp = composite_document(doc, apply_view_effects=False)
        b64 = base64.b64encode(_rgba_to_png_bytes(comp)).decode("ascii")
        creds = build_content_credentials_manifest(doc, comp)
        pins_html = ""
        comments_html = ""
        for idx, c in enumerate(doc.comments, start=1):
            px = c.x / max(doc.width, 1) * 100.0
            py = c.y / max(doc.height, 1) * 100.0
            status = "Resolved" if c.resolved else "Open"
            pins_html += f'<div class="pin" style="left:{px:.2f}%;top:{py:.2f}%" title="{c.author}: {c.text}">{idx}</div>'
            comments_html += (
                f'<div class="comment"><b>#{idx} {c.author}</b> <span class="tag">{status}</span>'
                f'<div class="ts">{c.timestamp}</div><p>{c.text}</p></div>'
            )
        if not comments_html:
            comments_html = '<p style="color:#94a3b8">No review comments pinned yet.</p>'

        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>KinoCloud Review — {doc.name}</title>
<style>
body{{margin:0;background:#12151C;color:#E6EAF2;font-family:'Segoe UI',sans-serif;display:flex;height:100vh}}
.stage{{flex:1;display:flex;align-items:center;justify-content:center;padding:24px;overflow:auto}}
.frame{{position:relative;display:inline-block;box-shadow:0 18px 50px rgba(0,0,0,.6);border:1px solid #2A3242}}
.frame img{{max-width:70vw;max-height:86vh;display:block}}
.pin{{position:absolute;transform:translate(-50%,-50%);width:24px;height:24px;border-radius:12px;background:#31A8FF;color:#0B1220;font-weight:700;font-size:12px;display:flex;align-items:center;justify-content:center;border:2px solid #fff}}
.side{{width:340px;background:#181C25;border-left:1px solid #2A3242;padding:18px;overflow:auto}}
.badge{{display:inline-block;background:#0E2238;color:#31A8FF;border:1px solid #1E5B94;border-radius:5px;padding:2px 8px;font-weight:700;font-size:12px}}
.comment{{background:#121620;border:1px solid #2A3242;border-radius:8px;padding:10px;margin:10px 0}}
.tag{{float:right;font-size:11px;color:#31A8FF}}.ts{{font-size:11px;color:#8D99AE}}
</style></head><body>
<div class="stage"><div class="frame"><img src="data:image/png;base64,{b64}"/>{pins_html}</div></div>
<div class="side"><span class="badge">KinoCloud Review</span><h2>{doc.name}</h2>
<p style="font-size:12px;color:#9AA4B8">{doc.width}x{doc.height} px · {doc.dpi} DPI · {doc.color_mode}<br/>SHA-256: {creds['asset_sha256'][:16]}…</p>
<h3>Review Comments ({len(doc.comments)})</h3>{comments_html}
<h3>Content Credentials</h3><pre style="font-size:11px;white-space:pre-wrap;color:#9AA4B8">{json.dumps(creds, indent=2)}</pre>
</div></body></html>"""
        with open(out_html, "w", encoding="utf-8") as f:
            f.write(html)
        return out_html


# ---------------------------------------------------------------------------
# Actions Recorder & Script Events Manager
# ---------------------------------------------------------------------------
class ActionManager:
    """Records & replays KinoShop Actions (.ksa) and manages Script Events triggers."""

    def __init__(self, config_dir: str) -> None:
        self.config_dir = config_dir
        os.makedirs(config_dir, exist_ok=True)
        self.recording: bool = False
        self.current_action_name: str = ""
        self.current_steps: List[Dict[str, Any]] = []
        self.actions: Dict[str, List[Dict[str, Any]]] = self._load_actions()
        self.script_events: Dict[str, str] = self._load_events()  # event_name -> python script code or path

    def _actions_path(self) -> str:
        return os.path.join(self.config_dir, "actions.ksa")

    def _events_path(self) -> str:
        return os.path.join(self.config_dir, "script_events.json")

    def _load_actions(self) -> Dict[str, List[Dict[str, Any]]]:
        p = self._actions_path()
        if os.path.isfile(p):
            try:
                return json.loads(open(p, "r", encoding="utf-8").read())
            except Exception:
                pass
        return {
            "Cinematic Pop & Vignette": [
                {"cmd": "add_adjustment", "params": {"type": "LUT / Color Lookup", "preset": "Cinema Teal & Orange", "intensity": 0.65}},
                {"cmd": "apply_filter", "params": {"name": "Unsharp Mask", "amount": 0.85, "radius": 1.6}},
                {"cmd": "apply_filter", "params": {"name": "Vignette", "amount": 0.35}},
            ],
            "Black & White High Contrast": [
                {"cmd": "add_adjustment", "params": {"type": "Black & White"}},
                {"cmd": "add_adjustment", "params": {"type": "Levels", "in_black": 18, "in_white": 238, "gamma": 1.05}},
            ],
        }

    def save_actions(self) -> None:
        with open(self._actions_path(), "w", encoding="utf-8") as f:
            json.dump(self.actions, f, indent=2)

    def _load_events(self) -> Dict[str, str]:
        p = self._events_path()
        if os.path.isfile(p):
            try:
                return json.loads(open(p, "r", encoding="utf-8").read())
            except Exception:
                pass
        return {"on_open": "", "on_save": "", "on_export": "", "on_new": ""}

    def save_events(self) -> None:
        with open(self._events_path(), "w", encoding="utf-8") as f:
            json.dump(self.script_events, f, indent=2)

    def start_recording(self, name: str) -> None:
        self.recording = True
        self.current_action_name = name
        self.current_steps = []

    def record_step(self, cmd: str, params: Optional[Dict[str, Any]] = None) -> None:
        if self.recording:
            self.current_steps.append({"cmd": cmd, "params": params or {}})

    def stop_recording(self) -> Optional[str]:
        if not self.recording:
            return None
        name = self.current_action_name or f"Action {len(self.actions) + 1}"
        if self.current_steps:
            self.actions[name] = list(self.current_steps)
            self.save_actions()
        self.recording = False
        self.current_steps = []
        return name
