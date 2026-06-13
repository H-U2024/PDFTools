# PDFBunkatsu

PDFファイルをGUIで分割し、PDFの各ページをWebP画像に変換するツールです。

## 使い方

依存関係をインストールします。

```powershell
.\.venv\Scripts\python.exe -m pip install pypdf PySide6 PyMuPDF Pillow
```

アプリを起動します。

```powershell
.\.venv\Scripts\python.exe main.py
```

## 機能

- PDF分割
  - 1ページずつ分割
  - 指定ページ数ごとに分割
  - 指定範囲を抽出、例: `1-3,5,8-`
- WebP変換
  - 複数PDFファイルを選択
  - PDFの各ページを出力先フォルダへまとめてWebPファイルとして保存
  - DPIとWebP品質を指定
