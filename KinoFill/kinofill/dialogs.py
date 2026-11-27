"""Dialogs for KinoFill (KinoSuite): Signatures Vault, Watermarks, Headers/Footers, Security, Merge/Split, Export."""

from __future__ import annotations

import base64
import io
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QMouseEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import get_signatures_dir
from .models import HeaderFooterConfig, PdfMetadata, SecurityConfig, WatermarkConfig
from .pdf_engine import (
    PAGE_PRESETS,
    clean_signature_image,
    get_available_signature_fonts,
    image_to_png_b64,
)


def _color_btn_style(hex_col: str) -> str:
    return f"QPushButton {{ background-color: {hex_col}; border: 1px solid #6B7280; border-radius: 4px; min-width: 28px; min-height: 22px; }}"


class SignatureDrawPad(QWidget):
    """Smooth high-DPI freehand signature drawing pad."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(460, 175)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.pen_color: str = "#0F172A"
        self.pen_width: float = 3.0
        self.strokes: List[Tuple[str, float, List[QPointF]]] = []
        self._cur: List[QPointF] = []

    def clear(self) -> None:
        self.strokes.clear()
        self._cur.clear()
        self.update()

    def undo_stroke(self) -> None:
        if self.strokes:
            self.strokes.pop()
            self.update()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._cur = [event.position()]
            self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._cur:
            self._cur.append(event.position())
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._cur:
            self.strokes.append((self.pen_color, self.pen_width, list(self._cur)))
            self._cur = []
            self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#D1D5DB"), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        # Subtle signature baseline
        base_y = int(self.height() * 0.76)
        p.setPen(QPen(QColor("#E5E7EB"), 1, Qt.PenStyle.DashLine))
        p.drawLine(24, base_y, self.width() - 24, base_y)
        p.setPen(QColor("#9CA3AF"))
        p.setFont(QFont("Segoe UI", 9))
        p.drawText(26, base_y + 16, "Sign above the line")

        all_strokes = list(self.strokes)
        if self._cur:
            all_strokes.append((self.pen_color, self.pen_width, self._cur))

        for col, width, pts in all_strokes:
            if not pts:
                continue
            p.setPen(QPen(QColor(col), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                path = QPainterPath()
                path.moveTo(pts[0])
                for i in range(1, len(pts) - 1):
                    mid = (pts[i] + pts[i + 1]) / 2.0
                    path.quadTo(pts[i], mid)
                path.lineTo(pts[-1])
                p.drawPath(path)
        p.end()

    def export_pil_image(self) -> Optional[Image.Image]:
        if not self.strokes:
            return None
        scale = 3.0
        w, h = int(self.width() * scale), int(self.height() * scale)
        qimg = QImage(w, h, QImage.Format.Format_ARGB32)
        qimg.fill(Qt.GlobalColor.transparent)
        p = QPainter(qimg)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(scale, scale)
        for col, width, pts in self.strokes:
            if not pts:
                continue
            p.setPen(QPen(QColor(col), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            if len(pts) == 1:
                p.drawPoint(pts[0])
            else:
                path = QPainterPath()
                path.moveTo(pts[0])
                for i in range(1, len(pts) - 1):
                    mid = (pts[i] + pts[i + 1]) / 2.0
                    path.quadTo(pts[i], mid)
                path.lineTo(pts[-1])
                p.drawPath(path)
        p.end()

        from PySide6.QtCore import QBuffer, QIODevice

        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        qimg.save(buf, "PNG")
        pil_img = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
        buf.close()
        bbox = pil_img.getbbox()
        if bbox:
            pad = 12
            pil_img = pil_img.crop(
                (max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(pil_img.width, bbox[2] + pad), min(pil_img.height, bbox[3] + pad))
            )
        return pil_img


class SignatureDialog(QDialog):
    """Full pdfFiller-style Signature & Initials creator + local saved vault."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Signature & Initials Manager")
        self.resize(640, 520)
        self.result_b64: str = ""
        self.result_ratio: float = 2.6
        self._uploaded_orig: Optional[Image.Image] = None
        self._uploaded_cleaned: Optional[Image.Image] = None
        self._type_color: str = "#0F172A"

        root = QVBoxLayout(self)

        # Saved vault strip
        vault_box = QGroupBox("Saved Signatures & Initials (Click to Use)")
        vault_lay = QHBoxLayout(vault_box)
        self.vault_list = QListWidget()
        self.vault_list.setFlow(QListWidget.Flow.LeftToRight)
        self.vault_list.setWrapping(False)
        self.vault_list.setIconSize(QSize(130, 52))
        self.vault_list.setFixedHeight(84)
        self.vault_list.itemDoubleClicked.connect(self._use_selected_vault)
        vault_lay.addWidget(self.vault_list, 1)

        vbtns = QVBoxLayout()
        btn_use_saved = QPushButton("Use Selected")
        btn_use_saved.setObjectName("PrimaryButton")
        btn_use_saved.clicked.connect(self._use_selected_vault)
        btn_del_saved = QPushButton("Delete")
        btn_del_saved.clicked.connect(self._delete_selected_vault)
        vbtns.addWidget(btn_use_saved)
        vbtns.addWidget(btn_del_saved)
        vault_lay.addLayout(vbtns)
        root.addWidget(vault_box)

        # Creator tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab 1: Draw
        draw_tab = QWidget()
        dl = QVBoxLayout(draw_tab)
        ctrl = QHBoxLayout()
        ctrl.addWidget(QLabel("Ink:"))
        for label, hx in [("Black", "#0F172A"), ("Blue", "#1D4ED8"), ("Red", "#B91C1C")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=hx: self._set_draw_color(c))
            ctrl.addWidget(b)
        ctrl.addSpacing(12)
        ctrl.addWidget(QLabel("Width:"))
        self.draw_width_slider = QSlider(Qt.Orientation.Horizontal)
        self.draw_width_slider.setRange(15, 70)
        self.draw_width_slider.setValue(30)
        self.draw_width_slider.setFixedWidth(100)
        self.draw_width_slider.valueChanged.connect(lambda v: setattr(self.draw_pad, "pen_width", v / 10.0))
        ctrl.addWidget(self.draw_width_slider)
        ctrl.addStretch()
        btn_undo = QPushButton("Undo")
        btn_undo.clicked.connect(lambda: self.draw_pad.undo_stroke())
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.draw_pad.clear())
        ctrl.addWidget(btn_undo)
        ctrl.addWidget(btn_clear)
        dl.addLayout(ctrl)

        self.draw_pad = SignatureDrawPad()
        dl.addWidget(self.draw_pad, 1)
        self.tabs.addTab(draw_tab, "Draw Signature")

        # Tab 2: Type
        type_tab = QWidget()
        tl = QVBoxLayout(type_tab)
        trow = QHBoxLayout()
        self.type_input = QLineEdit()
        self.type_input.setPlaceholderText("Type your full name or initials...")
        self.type_input.setText("Jane Doe")
        self.type_input.textChanged.connect(self._refresh_type_preview)
        trow.addWidget(self.type_input, 2)

        self.font_combo = QComboBox()
        self._sig_fonts = get_available_signature_fonts()
        for disp, _ in self._sig_fonts:
            self.font_combo.addItem(disp)
        self.font_combo.currentIndexChanged.connect(self._refresh_type_preview)
        trow.addWidget(self.font_combo, 1)

        for label, hx in [("Black", "#0F172A"), ("Blue", "#1D4ED8")]:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, c=hx: (setattr(self, "_type_color", c), self._refresh_type_preview()))
            trow.addWidget(b)
        tl.addLayout(trow)

        self.type_preview = QLabel()
        self.type_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.type_preview.setMinimumHeight(150)
        self.type_preview.setStyleSheet("background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 6px;")
        tl.addWidget(self.type_preview, 1)
        self.tabs.addTab(type_tab, "Type Signature")

        # Tab 3: Upload Image
        up_tab = QWidget()
        ul = QVBoxLayout(up_tab)
        urow = QHBoxLayout()
        btn_browse = QPushButton("Choose Signature Image (PNG/JPG)...")
        btn_browse.clicked.connect(self._browse_signature_image)
        urow.addWidget(btn_browse)
        self.chk_rm_bg = QCheckBox("Remove White Background")
        self.chk_rm_bg.setChecked(True)
        self.chk_rm_bg.toggled.connect(self._refresh_upload_preview)
        urow.addWidget(self.chk_rm_bg)
        urow.addWidget(QLabel("Threshold:"))
        self.thresh_slider = QSlider(Qt.Orientation.Horizontal)
        self.thresh_slider.setRange(120, 250)
        self.thresh_slider.setValue(215)
        self.thresh_slider.setFixedWidth(120)
        self.thresh_slider.valueChanged.connect(self._refresh_upload_preview)
        urow.addWidget(self.thresh_slider)
        urow.addStretch()
        ul.addLayout(urow)

        self.upload_preview = QLabel("Upload a photo or scan of your handwritten signature.")
        self.upload_preview.setObjectName("UploadPreview")
        self.upload_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.upload_preview.setMinimumHeight(150)
        ul.addWidget(self.upload_preview, 1)
        self.tabs.addTab(up_tab, "Upload Image")

        # Footer
        foot = QHBoxLayout()
        self.chk_save_vault = QCheckBox("Save to my Signatures Vault for future PDFs")
        self.chk_save_vault.setChecked(True)
        foot.addWidget(self.chk_save_vault)
        foot.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_apply = QPushButton("Place Signature")
        btn_apply.setObjectName("PrimaryButton")
        btn_apply.clicked.connect(self._accept_created)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_apply)
        root.addLayout(foot)

        self._load_vault()
        self._refresh_type_preview()

    def _set_draw_color(self, hex_col: str) -> None:
        self.draw_pad.pen_color = hex_col

    def _load_vault(self) -> None:
        self.vault_list.clear()
        sdir = get_signatures_dir()
        for p in sorted(sdir.glob("*.png"), reverse=True):
            px = QPixmap(str(p))
            if px.isNull():
                continue
            item = QListWidgetItem(QIcon(px), "")
            item.setData(Qt.ItemDataRole.UserRole, str(p))
            item.setToolTip(p.name)
            self.vault_list.addItem(item)

    def _use_selected_vault(self) -> None:
        cur = self.vault_list.currentItem()
        if not cur:
            return
        path = cur.data(Qt.ItemDataRole.UserRole)
        img = Image.open(path).convert("RGBA")
        self.result_b64 = image_to_png_b64(img)
        self.result_ratio = img.width / max(1, img.height)
        self.accept()

    def _delete_selected_vault(self) -> None:
        cur = self.vault_list.currentItem()
        if not cur:
            return
        path = Path(cur.data(Qt.ItemDataRole.UserRole))
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        self._load_vault()

    def _render_typed_signature(self) -> Optional[Image.Image]:
        text = self.type_input.text().strip()
        if not text:
            return None
        idx = max(0, self.font_combo.currentIndex())
        _, font_path = self._sig_fonts[idx]
        font_size = 96
        try:
            font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        tmp = Image.new("RGBA", (1400, 320), (255, 255, 255, 0))
        draw = ImageDraw.Draw(tmp)
        qc = QColor(self._type_color)
        draw.text((40, 60), text, font=font, fill=(qc.red(), qc.green(), qc.blue(), 255))
        bbox = tmp.getbbox()
        if not bbox:
            return None
        pad = 14
        return tmp.crop((max(0, bbox[0] - pad), max(0, bbox[1] - pad), min(tmp.width, bbox[2] + pad), min(tmp.height, bbox[3] + pad)))

    def _refresh_type_preview(self) -> None:
        img = self._render_typed_signature()
        if img is None:
            self.type_preview.setText("Type your signature above")
            return
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        px = QPixmap()
        px.loadFromData(buf.getvalue(), "PNG")
        self.type_preview.setPixmap(px.scaled(520, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _browse_signature_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Signature Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not path:
            return
        self._uploaded_orig = Image.open(path)
        self._refresh_upload_preview()

    def _refresh_upload_preview(self) -> None:
        if self._uploaded_orig is None:
            return
        self._uploaded_cleaned = clean_signature_image(
            self._uploaded_orig, threshold=self.thresh_slider.value(), remove_bg=self.chk_rm_bg.isChecked()
        )
        buf = io.BytesIO()
        self._uploaded_cleaned.save(buf, format="PNG")
        px = QPixmap()
        px.loadFromData(buf.getvalue(), "PNG")
        self.upload_preview.setPixmap(px.scaled(520, 135, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _accept_created(self) -> None:
        tab_idx = self.tabs.currentIndex()
        img: Optional[Image.Image] = None
        if tab_idx == 0:
            img = self.draw_pad.export_pil_image()
        elif tab_idx == 1:
            img = self._render_typed_signature()
        elif tab_idx == 2:
            img = self._uploaded_cleaned

        if img is None:
            QMessageBox.warning(self, "Empty Signature", "Please draw, type, or upload a signature first.")
            return

        if self.chk_save_vault.isChecked():
            out_path = get_signatures_dir() / f"sig_{int(time.time() * 1000)}.png"
            img.save(out_path, format="PNG")

        self.result_b64 = image_to_png_b64(img)
        self.result_ratio = img.width / max(1, img.height)
        self.accept()


class WatermarkDialog(QDialog):
    def __init__(self, cfg: WatermarkConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Watermark Settings")
        self.resize(400, 300)
        self._color = cfg.color

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.chk_enabled = QCheckBox("Enable Watermark on Document")
        self.chk_enabled.setChecked(cfg.enabled)
        form.addRow(self.chk_enabled)

        self.txt_text = QLineEdit(cfg.text)
        form.addRow("Watermark Text:", self.txt_text)

        self.spn_size = QSpinBox()
        self.spn_size.setRange(14, 160)
        self.spn_size.setValue(int(cfg.font_size))
        form.addRow("Font Size (pt):", self.spn_size)

        self.spn_angle = QSpinBox()
        self.spn_angle.setRange(-90, 90)
        self.spn_angle.setValue(int(cfg.angle))
        form.addRow("Angle (deg):", self.spn_angle)

        self.spn_opacity = QSpinBox()
        self.spn_opacity.setRange(5, 100)
        self.spn_opacity.setSuffix("%")
        self.spn_opacity.setValue(int(round(cfg.opacity * 100)))
        form.addRow("Opacity:", self.spn_opacity)

        self.btn_color = QPushButton()
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)
        form.addRow("Color:", self.btn_color)

        self.txt_pages = QLineEdit(cfg.page_range or "all")
        self.txt_pages.setPlaceholderText("all or 1-3, 5")
        form.addRow("Pages:", self.txt_pages)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._color), self, "Watermark Color")
        if col.isValid():
            self._color = col.name()
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def to_config(self) -> WatermarkConfig:
        return WatermarkConfig(
            enabled=self.chk_enabled.isChecked(),
            text=self.txt_text.text().strip(),
            font_size=float(self.spn_size.value()),
            color=self._color,
            opacity=self.spn_opacity.value() / 100.0,
            angle=float(self.spn_angle.value()),
            page_range=self.txt_pages.text().strip() or "all",
        )


class HeaderFooterDialog(QDialog):
    def __init__(self, cfg: HeaderFooterConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Headers, Footers & Page Numbers")
        self.resize(460, 360)
        self._color = cfg.color

        lay = QVBoxLayout(self)
        self.chk_enabled = QCheckBox("Enable Headers & Footers")
        self.chk_enabled.setChecked(cfg.enabled)
        lay.addWidget(self.chk_enabled)

        hint = QLabel("Tip: Use {page} for current page number and {total} for total pages.")
        hint.setObjectName("MutedHint")
        lay.addWidget(hint)

        form = QFormLayout()
        self.h_left = QLineEdit(cfg.header_left)
        self.h_center = QLineEdit(cfg.header_center)
        self.h_right = QLineEdit(cfg.header_right)
        self.f_left = QLineEdit(cfg.footer_left)
        self.f_center = QLineEdit(cfg.footer_center)
        self.f_right = QLineEdit(cfg.footer_right)

        form.addRow("Header Left:", self.h_left)
        form.addRow("Header Center:", self.h_center)
        form.addRow("Header Right:", self.h_right)
        form.addRow("Footer Left:", self.f_left)
        form.addRow("Footer Center:", self.f_center)
        form.addRow("Footer Right:", self.f_right)

        self.spn_size = QDoubleSpinBox()
        self.spn_size.setRange(6.0, 24.0)
        self.spn_size.setValue(cfg.font_size)
        form.addRow("Font Size (pt):", self.spn_size)

        self.spn_start = QSpinBox()
        self.spn_start.setRange(1, 9999)
        self.spn_start.setValue(cfg.start_page)
        form.addRow("Start at Page:", self.spn_start)

        self.btn_color = QPushButton()
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)
        form.addRow("Text Color:", self.btn_color)

        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._color), self, "Header/Footer Color")
        if col.isValid():
            self._color = col.name()
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def to_config(self) -> HeaderFooterConfig:
        return HeaderFooterConfig(
            enabled=self.chk_enabled.isChecked(),
            header_left=self.h_left.text(),
            header_center=self.h_center.text(),
            header_right=self.h_right.text(),
            footer_left=self.f_left.text(),
            footer_center=self.f_center.text(),
            footer_right=self.f_right.text(),
            font_size=self.spn_size.value(),
            color=self._color,
            start_page=self.spn_start.value(),
        )


class SecurityDialog(QDialog):
    def __init__(self, cfg: SecurityConfig, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Security, Protection & Save Options")
        self.resize(440, 290)
        lay = QVBoxLayout(self)

        sec_box = QGroupBox("Password Encryption")
        sf = QFormLayout(sec_box)
        self.chk_encrypt = QCheckBox("Encrypt saved PDF with password")
        self.chk_encrypt.setChecked(cfg.encrypt)
        sf.addRow(self.chk_encrypt)
        self.txt_user_pw = QLineEdit(cfg.user_password)
        self.txt_user_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_user_pw.setPlaceholderText("Password required to open PDF")
        sf.addRow("Open Password:", self.txt_user_pw)
        self.txt_owner_pw = QLineEdit(cfg.owner_password)
        self.txt_owner_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_owner_pw.setPlaceholderText("Optional owner/permissions password")
        sf.addRow("Owner Password:", self.txt_owner_pw)
        lay.addWidget(sec_box)

        opt_box = QGroupBox("Form & Redaction Save Behavior")
        ol = QVBoxLayout(opt_box)
        self.chk_flatten = QCheckBox("Flatten form fields permanently into page (recommended when sending completed forms)")
        self.chk_flatten.setChecked(cfg.flatten_forms)
        ol.addWidget(self.chk_flatten)

        self.chk_true_redact = QCheckBox("True Redaction: rasterize redacted pages so blacked-out text is permanently destroyed")
        self.chk_true_redact.setChecked(cfg.true_redact)
        ol.addWidget(self.chk_true_redact)
        lay.addWidget(opt_box)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def to_config(self) -> SecurityConfig:
        return SecurityConfig(
            encrypt=self.chk_encrypt.isChecked(),
            user_password=self.txt_user_pw.text(),
            owner_password=self.txt_owner_pw.text(),
            flatten_forms=self.chk_flatten.isChecked(),
            true_redact=self.chk_true_redact.isChecked(),
        )


class MetadataDialog(QDialog):
    def __init__(self, meta: PdfMetadata, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Document Properties & Metadata")
        self.resize(420, 240)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.txt_title = QLineEdit(meta.title)
        self.txt_author = QLineEdit(meta.author)
        self.txt_subject = QLineEdit(meta.subject)
        self.txt_keywords = QLineEdit(meta.keywords)
        self.txt_creator = QLineEdit(meta.creator or "KinoFill")
        form.addRow("Title:", self.txt_title)
        form.addRow("Author:", self.txt_author)
        form.addRow("Subject:", self.txt_subject)
        form.addRow("Keywords:", self.txt_keywords)
        form.addRow("Creator:", self.txt_creator)
        lay.addLayout(form)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def to_metadata(self) -> PdfMetadata:
        return PdfMetadata(
            title=self.txt_title.text().strip(),
            author=self.txt_author.text().strip(),
            subject=self.txt_subject.text().strip(),
            keywords=self.txt_keywords.text().strip(),
            creator=self.txt_creator.text().strip() or "KinoFill",
        )


class MergePdfsDialog(QDialog):
    def __init__(self, initial_files: Optional[List[str]] = None, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Merge Multiple PDFs")
        self.resize(520, 360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("Add and order the PDF files you want to combine into one PDF:"))

        row = QHBoxLayout()
        self.file_list = QListWidget()
        for f in initial_files or []:
            self.file_list.addItem(f)
        row.addWidget(self.file_list, 1)

        btns = QVBoxLayout()
        b_add = QPushButton("Add PDFs...")
        b_add.clicked.connect(self._add_files)
        b_up = QPushButton("Move Up")
        b_up.clicked.connect(lambda: self._move(-1))
        b_dn = QPushButton("Move Down")
        b_dn.clicked.connect(lambda: self._move(1))
        b_rm = QPushButton("Remove")
        b_rm.clicked.connect(self._remove)
        for b in (b_add, b_up, b_dn, b_rm):
            btns.addWidget(b)
        btns.addStretch()
        row.addLayout(btns)
        lay.addLayout(row, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Merge & Save...")
        bb.accepted.connect(self._validate_accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF Files", "", "PDF Files (*.pdf)")
        for f in files:
            self.file_list.addItem(f)

    def _move(self, delta: int) -> None:
        row = self.file_list.currentRow()
        if row < 0:
            return
        nxt = row + delta
        if 0 <= nxt < self.file_list.count():
            item = self.file_list.takeItem(row)
            self.file_list.insertItem(nxt, item)
            self.file_list.setCurrentRow(nxt)

    def _remove(self) -> None:
        row = self.file_list.currentRow()
        if row >= 0:
            self.file_list.takeItem(row)

    def _validate_accept(self) -> None:
        if self.file_list.count() < 2:
            QMessageBox.warning(self, "Add Files", "Please add at least 2 PDF files to merge.")
            return
        self.accept()

    def selected_files(self) -> List[str]:
        return [self.file_list.item(i).text() for i in range(self.file_list.count())]


class SplitPdfDialog(QDialog):
    def __init__(self, total_pages: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Split / Extract PDF Pages")
        self.resize(400, 210)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Document has {total_pages} page(s)."))

        self.rad_extract = QRadioButton("Extract page range into a single new PDF:")
        self.rad_extract.setChecked(True)
        lay.addWidget(self.rad_extract)

        self.txt_range = QLineEdit(f"1-{total_pages}")
        self.txt_range.setPlaceholderText("e.g. 1-3, 5, 8")
        lay.addWidget(self.txt_range)

        self.rad_burst = QRadioButton("Burst selected range into individual 1-page PDF files (choose folder)")
        lay.addWidget(self.rad_burst)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def is_burst(self) -> bool:
        return self.rad_burst.isChecked()

    def page_range(self) -> str:
        return self.txt_range.text().strip() or "all"


class NewBlankPdfDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Create New Blank PDF")
        self.resize(360, 200)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_size = QComboBox()
        for name in PAGE_PRESETS.keys():
            self.cmb_size.addItem(name)
        form.addRow("Page Size:", self.cmb_size)

        self.cmb_orient = QComboBox()
        self.cmb_orient.addItems(["Portrait", "Landscape"])
        form.addRow("Orientation:", self.cmb_orient)

        self.spn_pages = QSpinBox()
        self.spn_pages.setRange(1, 200)
        self.spn_pages.setValue(1)
        form.addRow("Pages:", self.spn_pages)

        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def get_params(self) -> Tuple[float, float, int]:
        w, h = PAGE_PRESETS[self.cmb_size.currentText()]
        if self.cmb_orient.currentText() == "Landscape":
            w, h = h, w
        return w, h, self.spn_pages.value()


class ExportImagesDialog(QDialog):
    def __init__(self, total_pages: int, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export PDF Pages to Images")
        self.resize(380, 210)
        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.cmb_fmt = QComboBox()
        self.cmb_fmt.addItems(["PNG", "JPEG"])
        form.addRow("Format:", self.cmb_fmt)

        self.cmb_dpi = QComboBox()
        self.cmb_dpi.addItems(["150", "200", "300"])
        self.cmb_dpi.setCurrentText("200")
        form.addRow("Resolution (DPI):", self.cmb_dpi)

        self.txt_range = QLineEdit(f"1-{total_pages}")
        form.addRow("Pages:", self.txt_range)

        lay.addLayout(form)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Choose Folder & Export...")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def get_params(self) -> Tuple[str, int, str]:
        return self.cmb_fmt.currentText(), int(self.cmb_dpi.currentText()), self.txt_range.text().strip() or "all"


class CustomStampDialog(QDialog):
    PRESETS = [
        ("APPROVED", "#15803D"),
        ("CONFIDENTIAL", "#DC2626"),
        ("DRAFT", "#D97706"),
        ("FINAL", "#1D4ED8"),
        ("PAID", "#047857"),
        ("VOID", "#B91C1C"),
        ("URGENT", "#EA580C"),
        ("SIGNED", "#2563EB"),
        ("COPY", "#4B5563"),
    ]

    def __init__(self, current_text: str, current_color: str, current_rot: float, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Rubber Stamp Designer")
        self.resize(400, 260)
        self._color = current_color

        lay = QVBoxLayout(self)
        presets_box = QGroupBox("Quick Presets")
        pl = QHBoxLayout(presets_box)
        self.cmb_preset = QComboBox()
        for t, _ in self.PRESETS:
            self.cmb_preset.addItem(t)
        self.cmb_preset.currentIndexChanged.connect(self._apply_preset)
        pl.addWidget(self.cmb_preset)
        lay.addWidget(presets_box)

        form = QFormLayout()
        self.txt_stamp = QLineEdit(current_text or "APPROVED")
        form.addRow("Stamp Text:", self.txt_stamp)

        self.spn_rot = QSpinBox()
        self.spn_rot.setRange(-45, 45)
        self.spn_rot.setValue(int(current_rot))
        form.addRow("Tilt Angle (deg):", self.spn_rot)

        self.btn_color = QPushButton()
        self.btn_color.setStyleSheet(_color_btn_style(self._color))
        self.btn_color.clicked.connect(self._pick_color)
        form.addRow("Stamp Color:", self.btn_color)
        lay.addLayout(form)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _apply_preset(self, idx: int) -> None:
        text, col = self.PRESETS[idx]
        self.txt_stamp.setText(text)
        self._color = col
        self.btn_color.setStyleSheet(_color_btn_style(col))

    def _pick_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._color), self, "Stamp Color")
        if col.isValid():
            self._color = col.name()
            self.btn_color.setStyleSheet(_color_btn_style(self._color))

    def get_params(self) -> Tuple[str, str, float]:
        return self.txt_stamp.text().strip() or "APPROVED", self._color, float(self.spn_rot.value())
