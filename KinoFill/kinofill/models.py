"""Data models for KinoFill annotations, form fields, and document state."""

from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class BaseItem:
    id: str = field(default_factory=new_id)
    kind: str = "base"
    page: int = 0
    x: float = 72.0
    y: float = 72.0
    w: float = 120.0
    h: float = 30.0
    opacity: float = 1.0
    rotation: float = 0.0
    locked: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EditableTextBlock:
    """A detected existing text span/line on a PDF page that can be clicked and edited directly."""

    id: str = field(default_factory=new_id)
    page: int = 0
    x: float = 0.0
    y: float = 0.0
    w: float = 0.0
    h: float = 0.0
    text: str = ""
    font_family: str = "Arial"
    font_size: float = 11.0
    bold: bool = False
    italic: bool = False
    color: str = "#111827"


@dataclass
class TextItem(BaseItem):
    kind: str = "text"
    text: str = "Text"
    font_family: str = "Arial"
    font_size: float = 12.0
    bold: bool = False
    italic: bool = False
    color: str = "#111827"
    bg_color: str = ""  # Empty means transparent
    bg_opacity: float = 1.0
    align: str = "left"  # left | center | right
    w: float = 180.0
    h: float = 28.0
    # When replacing existing PDF text, mask_rect covers the exact original text bounds
    mask_rect: Optional[List[float]] = None  # [mx, my, mw, mh] in visual PDF pts
    mask_color: str = ""
    source_block_id: str = ""
    source_orig_text: str = ""


@dataclass
class WhiteoutItem(BaseItem):
    kind: str = "whiteout"
    fill_color: str = "#FFFFFF"
    border_color: str = ""
    w: float = 140.0
    h: float = 24.0


@dataclass
class RedactItem(BaseItem):
    kind: str = "redact"
    fill_color: str = "#000000"
    label: str = ""
    w: float = 160.0
    h: float = 24.0


@dataclass
class HighlightItem(BaseItem):
    kind: str = "highlight"
    style: str = "highlight"  # highlight | underline | strikeout
    color: str = "#FDE047"
    opacity: float = 0.42
    w: float = 160.0
    h: float = 18.0


@dataclass
class InkItem(BaseItem):
    kind: str = "ink"
    points: List[List[float]] = field(default_factory=list)  # [[x, y], ...]
    color: str = "#1D4ED8"
    stroke_width: float = 2.2
    opacity: float = 1.0


@dataclass
class ShapeItem(BaseItem):
    kind: str = "shape"
    shape_type: str = "rect"  # rect | roundrect | ellipse | line | arrow
    stroke_color: str = "#DC2626"
    fill_color: str = ""  # empty = no fill
    stroke_width: float = 2.0
    opacity: float = 1.0
    x2: float = 192.0
    y2: float = 102.0


@dataclass
class StampItem(BaseItem):
    kind: str = "stamp"
    stamp_type: str = "check"  # check | cross | dot | circle | date | rubber
    text: str = "APPROVED"
    color: str = "#111827"
    border: bool = True
    w: float = 22.0
    h: float = 22.0


@dataclass
class ImageItem(BaseItem):
    kind: str = "image"
    image_b64: str = ""  # PNG base64
    is_signature: bool = False
    aspect_lock: bool = True
    w: float = 160.0
    h: float = 64.0


@dataclass
class NoteItem(BaseItem):
    kind: str = "note"
    text: str = ""
    author: str = "User"
    color: str = "#FEF08A"
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M"))
    w: float = 24.0
    h: float = 24.0


@dataclass
class FormFieldItem(BaseItem):
    kind: str = "form_field"
    field_name: str = ""
    field_type: str = "text"  # text | checkbox | radio | dropdown
    value: str = ""
    checked: bool = False
    checked_value: str = "/Yes"
    options: List[str] = field(default_factory=list)
    font_size: float = 10.5
    multiline: bool = False
    is_existing: bool = True
    radio_group: str = ""
    w: float = 160.0
    h: float = 24.0


ITEM_CLASS_MAP = {
    "text": TextItem,
    "whiteout": WhiteoutItem,
    "redact": RedactItem,
    "highlight": HighlightItem,
    "ink": InkItem,
    "shape": ShapeItem,
    "stamp": StampItem,
    "image": ImageItem,
    "note": NoteItem,
    "form_field": FormFieldItem,
}


def item_from_dict(data: Dict[str, Any]) -> BaseItem:
    kind = data.get("kind", "text")
    cls = ITEM_CLASS_MAP.get(kind, BaseItem)
    valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
    filtered = {k: v for k, v in data.items() if k in valid_fields}
    return cls(**filtered)


@dataclass
class WatermarkConfig:
    enabled: bool = False
    text: str = "CONFIDENTIAL"
    font_size: float = 54.0
    color: str = "#DC2626"
    opacity: float = 0.18
    angle: float = 42.0
    page_range: str = "all"  # "all" or "1-3,5"


@dataclass
class HeaderFooterConfig:
    enabled: bool = False
    header_left: str = ""
    header_center: str = ""
    header_right: str = ""
    footer_left: str = ""
    footer_center: str = "Page {page} of {total}"
    footer_right: str = ""
    font_size: float = 9.5
    color: str = "#4B5563"
    margin: float = 28.0
    start_page: int = 1


@dataclass
class SecurityConfig:
    encrypt: bool = False
    user_password: str = ""
    owner_password: str = ""
    flatten_forms: bool = False
    true_redact: bool = True


@dataclass
class PdfMetadata:
    title: str = ""
    author: str = ""
    subject: str = ""
    keywords: str = ""
    creator: str = "KinoFill"


class DocumentState:
    """In-memory state of an open PDF document tab with full undo/redo."""

    def __init__(self, source_path: str = "", working_pdf_path: str = "") -> None:
        self.source_path: str = source_path
        self.working_pdf_path: str = working_pdf_path
        self.password: str = ""
        self.items: List[BaseItem] = []
        self.text_blocks: Dict[int, List[EditableTextBlock]] = {}
        self.watermark: WatermarkConfig = WatermarkConfig()
        self.header_footer: HeaderFooterConfig = HeaderFooterConfig()
        self.security: SecurityConfig = SecurityConfig()
        self.metadata: PdfMetadata = PdfMetadata()
        self.dirty: bool = False
        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self.max_history: int = 80

    def replaced_block_ids(self, page_idx: int) -> set[str]:
        return {
            it.source_block_id
            for it in self.items
            if isinstance(it, TextItem) and it.page == page_idx and it.source_block_id
        }

    def snapshot(self) -> List[Dict[str, Any]]:
        return [item.to_dict() for item in self.items]

    def push_undo(self) -> None:
        self._undo_stack.append(self.snapshot())
        if len(self._undo_stack) > self.max_history:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self.dirty = True

    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append(self.snapshot())
        prev = self._undo_stack.pop()
        self.items = [item_from_dict(d) for d in prev]
        self.dirty = True
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append(self.snapshot())
        nxt = self._redo_stack.pop()
        self.items = [item_from_dict(d) for d in nxt]
        self.dirty = True
        return True

    def items_on_page(self, page_idx: int) -> List[BaseItem]:
        return [it for it in self.items if it.page == page_idx]

    def find_item(self, item_id: str) -> Optional[BaseItem]:
        for it in self.items:
            if it.id == item_id:
                return it
        return None

    def add_item(self, item: BaseItem, record_undo: bool = True) -> BaseItem:
        if record_undo:
            self.push_undo()
        self.items.append(item)
        self.dirty = True
        return item

    def remove_item(self, item_id: str, record_undo: bool = True) -> bool:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                if record_undo:
                    self.push_undo()
                self.items.pop(i)
                self.dirty = True
                return True
        return False

    def bring_to_front(self, item_id: str) -> bool:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                self.push_undo()
                self.items.append(self.items.pop(i))
                return True
        return False

    def send_to_back(self, item_id: str) -> bool:
        for i, it in enumerate(self.items):
            if it.id == item_id:
                self.push_undo()
                self.items.insert(0, self.items.pop(i))
                return True
        return False

    def remap_pages(self, old_to_new: Dict[int, int]) -> None:
        """Update item page indices after page reorder/delete/insert."""
        new_items: List[BaseItem] = []
        for it in self.items:
            if it.page in old_to_new:
                it.page = old_to_new[it.page]
                new_items.append(it)
        self.items = new_items
        self.dirty = True

    def duplicate_page_items(self, src_page: int, dst_page: int) -> None:
        clones: List[BaseItem] = []
        for it in self.items:
            if it.page == src_page:
                d = copy.deepcopy(it.to_dict())
                d["id"] = new_id()
                d["page"] = dst_page
                clones.append(item_from_dict(d))
        self.items.extend(clones)

    def to_project_json(self) -> str:
        payload = {
            "version": 1,
            "source_path": self.source_path,
            "items": [it.to_dict() for it in self.items],
            "watermark": asdict(self.watermark),
            "header_footer": asdict(self.header_footer),
            "metadata": asdict(self.metadata),
        }
        return json.dumps(payload, indent=2)

    def load_project_json(self, raw: str) -> None:
        data = json.loads(raw)
        self.items = [item_from_dict(d) for d in data.get("items", [])]
        if "watermark" in data:
            self.watermark = WatermarkConfig(**data["watermark"])
        if "header_footer" in data:
            self.header_footer = HeaderFooterConfig(**data["header_footer"])
        if "metadata" in data:
            self.metadata = PdfMetadata(**data["metadata"])
        self._undo_stack.clear()
        self._redo_stack.clear()
        self.dirty = False
