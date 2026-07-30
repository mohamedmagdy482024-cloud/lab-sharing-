from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QScrollArea, QWidget, QLabel, QFrame, QPushButton, QHBoxLayout
)
from PyQt6.QtCore import Qt

STEPS = [
    ("💾 Commit", "#f9e2af",
     "Save a snapshot of your current changes.\n"
     "→ Type a message describing what changed, then press Commit.\n"
     "→ Only changed files are saved — unchanged files stay as-is.\n"
     "→ Tip: commit often, one logical change per commit."),

    ("⬆ Push  (Client only)", "#89b4fa",
     "Send your commits to the Main device.\n"
     "→ Main device must be running Lab Sharing.\n"
     "→ Only your new commits are sent — nothing else."),

    ("⬇ Pull", "#a6e3a1",
     "Get the latest commits from the other device.\n"
     "→ Only new changes come in — your files stay safe.\n"
     "→ If there are conflicts, the Live Log will tell you which files."),

    ("↩ Revert", "#f38ba8",
     "Go back to a previous commit.\n"
     "→ Look at the Live Log for commit IDs.\n"
     "→ Copy the commit ID (e.g. 9e1a4607) into the message box.\n"
     "→ Press Revert — your files go back to exactly that point."),

    ("📂 Change Repo", "#cba6f7",
     "Switch to a different project folder.\n"
     "→ Opens a folder picker — select the new project.\n"
     "→ If the folder already has .git it connects to it.\n"
     "→ If not, it initializes a new repo there."),

    ("📁 Transfer — Browse", "#a6adc8",
     "Send any file or folder to another device.\n"
     "→ Press Browse — a dialog opens to pick a file first.\n"
     "→ If you close it without picking, it opens again for a folder.\n"
     "→ Then press Send to Device — other device must press Receive first."),

    ("🖥️ Main vs 💻 Client", "#f9e2af",
     "Main device = you — owns the repo.\n"
     "→ Runs git daemon so others can connect.\n"
     "→ Can Commit and Pull.\n\n"
     "Client device = your colleague.\n"
     "→ Clones from Main on first setup.\n"
     "→ Can Commit, Push, and Pull."),

    ("🔄 Typical workflow", "#a6adc8",
     "1. You (Main): make changes → Commit\n"
     "2. Colleague (Client): Pull → see your changes\n"
     "3. Colleague: make changes → Commit → Push\n"
     "4. You (Main): Pull → get colleague's changes\n"
     "5. Repeat ✅"),
]


class GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📖 Lab Sharing — Usage Guide")
        self.setMinimumSize(480, 580)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e2e; color: #cdd6f4; }
            QScrollArea { border: none; background: transparent; }
            QWidget#scroll_content { background: transparent; }
        """)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header
        hdr = QWidget()
        hdr.setStyleSheet("background-color:#181825;")
        hl = QVBoxLayout(hdr)
        hl.setContentsMargins(20, 14, 20, 12)
        t = QLabel("📖  Usage Guide")
        t.setStyleSheet("color:#89b4fa; font-size:16px; font-weight:bold;")
        s = QLabel("Step-by-step guide for every button")
        s.setStyleSheet("color:#6c7086; font-size:11px;")
        hl.addWidget(t); hl.addWidget(s)
        root.addWidget(hdr)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:#313244;"); div.setFixedHeight(1)
        root.addWidget(div)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        content = QWidget(); content.setObjectName("scroll_content")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 14, 20, 14); cl.setSpacing(10)

        for title, color, desc in STEPS:
            card = QFrame()
            card.setStyleSheet("QFrame{background-color:#181825;border-radius:8px;border:1px solid #313244;}")
            fl = QVBoxLayout(card)
            fl.setContentsMargins(14, 12, 14, 12); fl.setSpacing(5)
            t_lbl = QLabel(title)
            t_lbl.setStyleSheet(f"color:{color};font-size:13px;font-weight:bold;background:transparent;")
            d_lbl = QLabel(desc)
            d_lbl.setStyleSheet("color:#a6adc8;font-size:12px;background:transparent;")
            d_lbl.setWordWrap(True)
            fl.addWidget(t_lbl); fl.addWidget(d_lbl)
            cl.addWidget(card)

        cl.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

        foot = QWidget(); foot.setStyleSheet("background-color:#181825;")
        fl2 = QHBoxLayout(foot)
        fl2.setContentsMargins(20, 10, 20, 10); fl2.addStretch()
        close_btn = QPushButton("✖  Close")
        close_btn.setStyleSheet("""
            QPushButton{background-color:#313244;color:#cdd6f4;border:none;
            border-radius:6px;padding:8px 20px;font-size:12px;}
            QPushButton:hover{background-color:#45475a;}
        """)
        close_btn.clicked.connect(self.close)
        fl2.addWidget(close_btn)
        root.addWidget(foot)
