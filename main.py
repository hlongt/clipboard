import sys
import hashlib
import os
import json
import shutil
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QListWidget,
                             QListWidgetItem, QLabel, QPushButton, QHBoxLayout,
                             QFileIconProvider)
from PyQt6.QtCore import Qt, QTimer, QSize, QMimeData, QUrl, QFileInfo
from PyQt6.QtGui import QPixmap, QFont, QImage

STORAGE_DIR  = "D:/cliplib"
IMAGE_DIR    = os.path.join(STORAGE_DIR, "images")
FILES_DIR    = os.path.join(STORAGE_DIR, "files")
INDEX_FILE   = os.path.join(STORAGE_DIR, "index.json")


def ensure_dirs():
    os.makedirs(STORAGE_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR,   exist_ok=True)
    os.makedirs(FILES_DIR,   exist_ok=True)


# ------------------------------------------------------------------ #
#  自定义条目 Widget                                                   #
# ------------------------------------------------------------------ #
class ClipboardItemWidget(QWidget):
    def __init__(self, time_str, _type, data):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        time_label = QLabel(time_str)
        time_label.setStyleSheet("color: #999; font-size: 10px;")
        time_label.setFixedWidth(145)
        layout.addWidget(time_label)

        if _type == "text":
            display_text = data.strip().replace("\n", " ")
            if len(display_text) > 40:
                display_text = display_text[:40] + "..."
            content_label = QLabel(display_text)
            content_label.setFont(QFont("Consolas", 10))
            content_label.setStyleSheet("color: #333;")
            layout.addWidget(content_label, 1)

        elif _type == "image":
            img_label = QLabel()
            pixmap = QPixmap(data) if isinstance(data, str) else QPixmap.fromImage(data)
            scaled = pixmap.scaled(60, 60, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            img_label.setPixmap(scaled)
            img_label.setFixedSize(60, 60)
            layout.addWidget(img_label)
            layout.addStretch(1)

        elif _type == "files":
            # data = [{"original": "...", "saved": "..."}, ...]
            file_layout = QVBoxLayout()
            file_layout.setSpacing(2)
            file_layout.setContentsMargins(0, 0, 0, 0)

            provider = QFileIconProvider()
            for f in data[:3]:
                original_path = f["original"]
                row = QHBoxLayout()
                row.setSpacing(6)

                icon_label = QLabel()
                fi = QFileInfo(original_path)
                icon_label.setPixmap(provider.icon(fi).pixmap(16, 16))
                icon_label.setFixedSize(16, 16)
                row.addWidget(icon_label)

                name = os.path.basename(original_path)
                if len(name) > 35:
                    name = name[:32] + "..."
                name_label = QLabel(name)
                name_label.setFont(QFont("Consolas", 10))
                name_label.setStyleSheet("color: #333;")
                row.addWidget(name_label)
                row.addStretch(1)
                file_layout.addLayout(row)

            if len(data) > 3:
                more_label = QLabel(f"  … 共 {len(data)} 个文件")
                more_label.setStyleSheet("color: #aaa; font-size: 10px;")
                file_layout.addWidget(more_label)

            layout.addLayout(file_layout)
            layout.addStretch(1)


# ------------------------------------------------------------------ #
#  主窗口                                                              #
# ------------------------------------------------------------------ #
class SmartClipboard(QWidget):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.history  = []
        self.last_hash = None

        self.init_ui()
        self.load_history()

        initial_mime   = QApplication.clipboard().mimeData()
        self.last_hash = self.get_content_hash(initial_mime)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_clipboard)
        self.timer.start(500)

    def init_ui(self):
        self.setWindowTitle("剪贴板管理器")
        self.setFixedWidth(580)
        self.setFixedHeight(600)
        self.setWindowFlags(Qt.WindowType.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)

        self.status_label = QLabel("监听中...")
        self.status_label.setStyleSheet("color: #999; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget::item { border-bottom: 1px solid #f0f0f0; }
            QListWidget::item:selected { background-color: #f5f5f5; color: #333; }
        """)
        self.list_widget.itemClicked.connect(self.copy_item_back)
        layout.addWidget(self.list_widget)

        self.clear_btn = QPushButton("清空历史记录")
        self.clear_btn.setFixedHeight(35)
        self.clear_btn.setStyleSheet("background-color: #eee; border: none; color: #666;")
        self.clear_btn.clicked.connect(self.clear_history)
        layout.addWidget(self.clear_btn)

    # ------------------------------------------------------------------ #
    #  持久化                                                              #
    # ------------------------------------------------------------------ #
    def save_index(self):
        records = []
        for entry in self.history:
            rec = {"type": entry["type"], "hash": entry["hash"], "time": entry["time"]}
            if entry["type"] == "text":
                rec["content"] = entry["content"]
            elif entry["type"] == "image":
                rec["image_path"] = entry.get("image_path", "")
            elif entry["type"] == "files":
                # 存原始路径 + 备份路径
                rec["content"] = entry["content"]   # [{"original":..., "saved":...}]
            records.append(rec)

        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def load_history(self):
        if not os.path.exists(INDEX_FILE):
            return
        try:
            with open(INDEX_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
        except Exception:
            return

        for rec in records:
            _type = rec.get("type")
            entry = {"type": _type, "hash": rec["hash"], "time": rec["time"]}

            if _type == "text":
                entry["content"] = rec.get("content", "")
                display_data = entry["content"]

            elif _type == "image":
                image_path = rec.get("image_path", "")
                entry["image_path"] = image_path
                if os.path.exists(image_path):
                    entry["content"] = QImage(image_path)
                    display_data = image_path
                else:
                    continue

            elif _type == "files":
                file_list = rec.get("content", [])
                # 过滤掉备份文件已丢失的条目
                valid = [f for f in file_list if os.path.exists(f["saved"])]
                if not valid:
                    continue
                entry["content"] = valid
                display_data = valid

            else:
                continue

            self.history.append(entry)
            self._append_list_item(_type, display_data, rec["time"], prepend=False)

        if self.history:
            self.last_hash = self.history[0]["hash"]

    # ------------------------------------------------------------------ #
    #  哈希                                                                #
    # ------------------------------------------------------------------ #
    def get_content_hash(self, mime_data):
        try:
            if mime_data.hasUrls():
                local_files = [u.toLocalFile() for u in mime_data.urls() if u.isLocalFile()]
                if local_files:
                    key = "|".join(sorted(local_files))
                    return hashlib.md5(key.encode("utf-8")).hexdigest()
            if mime_data.hasImage():
                image = QApplication.clipboard().image()
                if not image.isNull():
                    ptr = image.constBits()
                    ptr.setsize(image.sizeInBytes())
                    return hashlib.md5(bytes(ptr)).hexdigest()
            if mime_data.hasText():
                text = mime_data.text()
                if text.strip():
                    return hashlib.md5(text.encode("utf-8")).hexdigest()
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    #  轮询                                                                #
    # ------------------------------------------------------------------ #
    def check_clipboard(self):
        clipboard  = QApplication.clipboard()
        mime_data  = clipboard.mimeData()
        current_hash = self.get_content_hash(mime_data)

        if current_hash is None or current_hash == self.last_hash:
            return
        self.last_hash = current_hash

        if mime_data.hasUrls():
            local_files = [u.toLocalFile() for u in mime_data.urls() if u.isLocalFile()]
            if local_files:
                self.add_to_history("files", local_files, current_hash)
                return

        if mime_data.hasImage():
            self.add_to_history("image", clipboard.image(), current_hash)
        elif mime_data.hasText():
            self.add_to_history("text", clipboard.text(), current_hash)

    # ------------------------------------------------------------------ #
    #  添加条目                                                            #
    # ------------------------------------------------------------------ #
    def _save_files(self, paths, content_hash):
        """
        把原始文件复制到 D:/cliplib/files/<hash>/ 子目录。
        返回 [{"original": 原路径, "saved": 备份路径}, ...]
        """
        dest_dir = os.path.join(FILES_DIR, content_hash)
        os.makedirs(dest_dir, exist_ok=True)

        result = []
        for src in paths:
            if not os.path.exists(src):
                continue
            filename = os.path.basename(src)
            dest = os.path.join(dest_dir, filename)

            # 文件名冲突时加序号
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(dest):
                dest = os.path.join(dest_dir, f"{base}_{counter}{ext}")
                counter += 1

            try:
                shutil.copy2(src, dest)
                result.append({"original": src, "saved": dest})
            except Exception:
                pass   # 无权限等情况跳过

        return result

    def add_to_history(self, _type, data, content_hash):
        full_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"type": _type, "hash": content_hash, "time": full_time}

        if _type == "text":
            entry["content"] = data
            display_data = data

        elif _type == "image":
            image_path = os.path.join(IMAGE_DIR, f"{content_hash}.png")
            if not os.path.exists(image_path):
                data.save(image_path, "PNG")
            entry["content"]    = data
            entry["image_path"] = image_path
            display_data = image_path

        elif _type == "files":
            file_list = self._save_files(data, content_hash)
            if not file_list:
                return   # 全部文件无法访问，不入库
            entry["content"] = file_list
            display_data = file_list

        self.history.insert(0, entry)
        self._append_list_item(_type, display_data, full_time, prepend=True)

        # 超出 50 条
        if len(self.history) > 50:
            oldest = self.history.pop()
            self.list_widget.takeItem(self.list_widget.count() - 1)
            self._delete_entry_files(oldest)

        self.save_index()

    def _delete_entry_files(self, entry):
        """删除某条记录对应的磁盘文件"""
        if entry["type"] == "image":
            img_path = entry.get("image_path", "")
            if img_path and os.path.exists(img_path):
                still_used = any(e.get("image_path") == img_path for e in self.history)
                if not still_used:
                    os.remove(img_path)

        elif entry["type"] == "files":
            # 删除整个 hash 子目录
            dest_dir = os.path.join(FILES_DIR, entry["hash"])
            if os.path.isdir(dest_dir):
                shutil.rmtree(dest_dir, ignore_errors=True)

    def _append_list_item(self, _type, display_data, time_str, prepend=False):
        item = QListWidgetItem()
        widget = ClipboardItemWidget(time_str, _type, display_data)

        if _type == "image":
            item.setSizeHint(QSize(0, 72))
        elif _type == "files":
            rows = min(len(display_data), 3) + (1 if len(display_data) > 3 else 0)
            item.setSizeHint(QSize(0, max(40, rows * 22 + 12)))
        else:
            item.setSizeHint(QSize(0, 40))

        if prepend:
            self.list_widget.insertItem(0, item)
        else:
            self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

    # ------------------------------------------------------------------ #
    #  点击恢复                                                            #
    # ------------------------------------------------------------------ #
    def copy_item_back(self, item):
        index = self.list_widget.row(item)
        entry = self.history[index]
        clipboard = QApplication.clipboard()

        self.timer.stop()
        self.last_hash = entry["hash"]

        if entry["type"] == "text":
            clipboard.setText(entry["content"])

        elif entry["type"] == "image":
            clipboard.setImage(entry["content"])

        elif entry["type"] == "files":
            # 恢复时把备份路径写入剪贴板，粘贴到资源管理器可直接操作
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(f["saved"]) for f in entry["content"]])
            clipboard.setMimeData(mime)

        self.status_label.setText(f"已恢复: {entry['time']}")
        QTimer.singleShot(100, self.timer.start)

    # ------------------------------------------------------------------ #
    #  清空                                                                #
    # ------------------------------------------------------------------ #
    def clear_history(self):
        for entry in self.history:
            self._delete_entry_files(entry)

        self.history.clear()
        self.list_widget.clear()

        with open(INDEX_FILE, "w", encoding="utf-8") as f:
            json.dump([], f)

        initial_mime   = QApplication.clipboard().mimeData()
        self.last_hash = self.get_content_hash(initial_mime)
        self.status_label.setText("历史已清空")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    manager = SmartClipboard()
    manager.show()
    sys.exit(app.exec())